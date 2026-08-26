from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from .api import ApiClient
from .config import Settings
from .downloader import Downloader
from .manifest import load_manifest, save_manifest
from .models import (
    DownloadResult,
    ManifestEntry,
    RemoteFile,
    SyncPlan,
    SyncResult,
)
from .paths import local_path_for


ProgressCallback = Callable[[str], None]


def build_sync_plan(
    remote_files: list[RemoteFile],
    manifest: dict[str, ManifestEntry],
    output_dir: Path,
    root: str,
) -> SyncPlan:
    remote_by_path = {item.path: item for item in remote_files}
    new: list[RemoteFile] = []
    changed: list[RemoteFile] = []
    missing: list[RemoteFile] = []

    for remote in remote_files:
        entry = manifest.get(remote.path)
        local_path = local_path_for(output_dir, remote.path, root)
        if entry is None:
            new.append(remote)
        elif entry.size != remote.size or entry.modified != remote.modified:
            changed.append(remote)
        elif not local_path.is_file() or local_path.stat().st_size != remote.size:
            missing.append(remote)

    removed = sorted(set(manifest) - set(remote_by_path))
    return SyncPlan(new=new, changed=changed, missing=missing, removed=removed)


class SyncEngine:
    def __init__(
        self,
        settings: Settings,
        api: ApiClient,
        *,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.settings = settings
        self.api = api
        self.progress = progress or (lambda _: None)

    async def discover(self) -> list[RemoteFile]:
        return await self.api.list_files(
            self.settings.root,
            search=".mp3",
            page_size=self.settings.page_size,
        )

    async def plan(self, remote_files: list[RemoteFile] | None = None) -> SyncPlan:
        remote_files = remote_files if remote_files is not None else await self.discover()
        manifest = load_manifest(self.settings.manifest_path)
        return build_sync_plan(
            remote_files,
            manifest,
            self.settings.output_dir,
            self.settings.root,
        )

    async def run(self) -> SyncResult:
        self.progress(f"Discovering files below {self.settings.root}/...")
        remote_files = await self.discover()
        manifest = load_manifest(self.settings.manifest_path)
        plan = build_sync_plan(
            remote_files,
            manifest,
            self.settings.output_dir,
            self.settings.root,
        )
        self.progress(
            f"Found {len(remote_files)} remote files: {len(plan.new)} new, "
            f"{len(plan.changed)} changed, {len(plan.missing)} missing locally."
        )

        status_by_path = {
            **{item.path: "new" for item in plan.new},
            **{item.path: "changed" for item in plan.changed},
            **{item.path: "missing" for item in plan.missing},
        }
        downloader = Downloader(
            self.api,
            retries=self.settings.retries,
            retry_delay=self.settings.retry_delay,
        )
        semaphore = asyncio.Semaphore(self.settings.concurrency)

        async def download_one(remote: RemoteFile) -> DownloadResult:
            async with semaphore:
                status = status_by_path[remote.path]
                self.progress(f"Downloading [{status}] {remote.path}")
                try:
                    destination = local_path_for(
                        self.settings.output_dir,
                        remote.path,
                        self.settings.root,
                    )
                    etag = await downloader.download(remote, destination)
                    return DownloadResult(remote=remote, status=status, etag=etag)
                except Exception as exc:  # Every file failure must not abort the remaining queue.
                    return DownloadResult(
                        remote=remote,
                        status=status,
                        error=f"{type(exc).__name__}: {exc}",
                    )

        tasks = [asyncio.create_task(download_one(item)) for item in plan.downloads]
        downloaded: list[DownloadResult] = []
        failed: list[DownloadResult] = []
        for task in asyncio.as_completed(tasks):
            result = await task
            if result.error:
                failed.append(result)
                self.progress(f"FAILED {result.remote.path}: {result.error}")
            else:
                downloaded.append(result)
                manifest[result.remote.path] = ManifestEntry.from_remote(
                    result.remote,
                    etag=result.etag,
                )
                # Persist each completed file so a container restart never causes a
                # successfully finalized file to be downloaded again.
                save_manifest(self.settings.manifest_path, manifest)
                self.progress(f"Saved {result.remote.path}")

        removed: list[str] = []
        cleanup_safe = bool(remote_files) or not manifest
        if self.settings.cleanup and not cleanup_safe:
            self.progress(
                "Cleanup skipped: the API returned no files while the manifest is non-empty."
            )
        if self.settings.cleanup and cleanup_safe:
            for remote_path in plan.removed:
                local_path = local_path_for(
                    self.settings.output_dir,
                    remote_path,
                    self.settings.root,
                )
                local_path.unlink(missing_ok=True)
                _remove_empty_parents(local_path.parent, self.settings.output_dir)
                manifest.pop(remote_path, None)
                removed.append(remote_path)
            if plan.removed:
                save_manifest(self.settings.manifest_path, manifest)

        # Ensure an empty/initially-current collection still gets a manifest.
        if not self.settings.manifest_path.exists():
            save_manifest(self.settings.manifest_path, manifest)

        unchanged = len(remote_files) - len(plan.downloads)
        return SyncResult(
            discovered=len(remote_files),
            downloaded=downloaded,
            failed=failed,
            removed=removed,
            unchanged=max(unchanged, 0),
        )


def _remove_empty_parents(directory: Path, boundary: Path) -> None:
    boundary = boundary.resolve()
    current = directory
    while current.exists() and current.resolve() != boundary:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent
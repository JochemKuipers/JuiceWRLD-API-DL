from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import httpx

from .api import ApiClient
from .models import RemoteFile


class DownloadError(RuntimeError):
    pass


class _RestartDownload(Exception):
    pass


class Downloader:
    def __init__(
        self,
        api: ApiClient,
        *,
        retries: int,
        retry_delay: float,
        chunk_size: int = 512 * 1024,
    ) -> None:
        self.api = api
        self.retries = retries
        self.retry_delay = retry_delay
        self.chunk_size = chunk_size

    async def download(self, remote: RemoteFile, destination: Path) -> str:
        destination.parent.mkdir(parents=True, exist_ok=True)
        part = destination.with_name(f"{destination.name}.part")
        metadata_path = destination.with_name(f"{destination.name}.part.meta.json")

        if part.exists() and not _partial_matches_remote(metadata_path, remote):
            _discard_partial(part, metadata_path)
        if part.exists() and part.stat().st_size == remote.size:
            etag = _read_etag(metadata_path)
            part.replace(destination)
            metadata_path.unlink(missing_ok=True)
            return etag
        if part.exists() and part.stat().st_size > remote.size:
            _discard_partial(part, metadata_path)

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                return await self._download_once(remote, destination, part, metadata_path)
            except _RestartDownload as exc:
                last_error = exc
                _discard_partial(part, metadata_path)
            except (httpx.HTTPError, OSError, DownloadError) as exc:
                last_error = exc
                if part.exists() and part.stat().st_size > remote.size:
                    _discard_partial(part, metadata_path)

            if attempt < self.retries:
                await asyncio.sleep(self.retry_delay * (2**attempt))

        raise DownloadError(
            f"Failed to download {remote.path!r} after {self.retries + 1} attempts: {last_error}"
        ) from last_error

    async def _download_once(
        self,
        remote: RemoteFile,
        destination: Path,
        part: Path,
        metadata_path: Path,
    ) -> str:
        offset = part.stat().st_size if part.exists() else 0
        saved_etag = _read_etag(metadata_path) if offset else ""

        async with self.api.stream_download(
            remote.path,
            offset=offset,
            etag=saved_etag,
        ) as response:
            if response.status_code == 416 and offset == remote.size:
                part.replace(destination)
                metadata_path.unlink(missing_ok=True)
                return saved_etag
            response.raise_for_status()

            response_etag = response.headers.get("etag", "")
            append = offset > 0 and response.status_code == httpx.codes.PARTIAL_CONTENT
            if append:
                content_range = response.headers.get("content-range", "")
                if not content_range.startswith(f"bytes {offset}-"):
                    raise _RestartDownload(
                        f"Server resumed {remote.path!r} at an unexpected offset: {content_range!r}"
                    )
                if saved_etag and response_etag and saved_etag != response_etag:
                    raise _RestartDownload(f"ETag changed while resuming {remote.path!r}")
            elif offset:
                # If-Range correctly returns 200 when the remote object changed.
                offset = 0

            etag = response_etag or (saved_etag if append else "")
            mode = "ab" if append else "wb"
            with part.open(mode) as handle:
                # Opening in wb mode truncates stale bytes before metadata says
                # this partial belongs to the current remote object.
                _write_partial_metadata(metadata_path, remote, etag)
                async for chunk in response.aiter_bytes(self.chunk_size):
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())

        actual_size = part.stat().st_size
        if remote.size and actual_size != remote.size:
            raise DownloadError(
                f"Size mismatch for {remote.path!r}: expected {remote.size}, got {actual_size}"
            )
        part.replace(destination)
        metadata_path.unlink(missing_ok=True)
        return etag


def _read_etag(path: Path) -> str:
    return str(_read_partial_metadata(path).get("etag") or "")


def _read_partial_metadata(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _partial_matches_remote(path: Path, remote: RemoteFile) -> bool:
    data = _read_partial_metadata(path)
    return data.get("size") == remote.size and data.get("modified") == remote.modified


def _write_partial_metadata(path: Path, remote: RemoteFile, etag: str) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(
                {
                    "size": remote.size,
                    "modified": remote.modified,
                    "etag": etag,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _discard_partial(part: Path, metadata_path: Path) -> None:
    part.unlink(missing_ok=True)
    metadata_path.unlink(missing_ok=True)
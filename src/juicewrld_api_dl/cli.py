from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path

import httpx

from .api import ApiClient
from .config import Settings
from .manifest import load_manifest
from .notify import notify_sync_complete, notify_sync_failed
from .sync import SyncEngine


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="juicewrld-api-dl",
        description="Mirror the Juice WRLD API Compilation folder and keep it up to date.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    sync = commands.add_parser("sync", help="Run one synchronization pass and exit.")
    _add_paths(sync)
    sync.add_argument("--concurrency", "-c", type=_positive_int)
    sync.add_argument("--cleanup", action=argparse.BooleanOptionalAction, default=None)

    watch = commands.add_parser("watch", help="Continuously synchronize at a fixed interval.")
    _add_paths(watch)
    watch.add_argument("--interval", "-i", type=_poll_interval)
    watch.add_argument("--concurrency", "-c", type=_positive_int)
    watch.add_argument("--cleanup", action=argparse.BooleanOptionalAction, default=None)

    status = commands.add_parser("status", help="Compare remote and local state.")
    _add_paths(status)

    listing = commands.add_parser("list", help="List remote Compilation files.")
    listing.add_argument("--limit", "-n", type=int, default=50)

    manifest = commands.add_parser("manifest", help="Inspect the local manifest.")
    manifest.add_argument("--config-dir", type=Path)
    manifest.add_argument("--json", action="store_true")
    return parser


def _add_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", "-o", type=Path, help="Output directory.")
    parser.add_argument("--config-dir", type=Path, help="Manifest directory.")


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _poll_interval(value: str) -> int:
    number = int(value)
    if number < 60:
        raise argparse.ArgumentTypeError("must be at least 60")
    return number


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    try:
        if args.command == "sync":
            settings = _settings(
                output_dir=args.out,
                config_dir=args.config_dir,
                concurrency=args.concurrency,
                cleanup=args.cleanup,
            )
            if asyncio.run(_run_sync(settings)):
                raise SystemExit(1)
        elif args.command == "watch":
            settings = _settings(
                output_dir=args.out,
                config_dir=args.config_dir,
                poll_interval=args.interval,
                concurrency=args.concurrency,
                cleanup=args.cleanup,
            )
            try:
                asyncio.run(_watch(settings))
            except KeyboardInterrupt:
                print("Stopped.")
        elif args.command == "status":
            asyncio.run(
                _status(_settings(output_dir=args.out, config_dir=args.config_dir))
            )
        elif args.command == "list":
            if args.limit < 0:
                parser.error("--limit must be at least 0")
            asyncio.run(_list_remote(_settings(), args.limit))
        else:
            _print_manifest(_settings(config_dir=args.config_dir), args.json)
    except ValueError as exc:
        parser.error(str(exc))


async def _run_sync(settings: Settings) -> bool:
    try:
        async with ApiClient(settings.api_url, timeout=settings.timeout) as api:
            result = await SyncEngine(settings, api, progress=print).run()
    except (httpx.HTTPError, OSError, ValueError) as exc:
        message = f"{type(exc).__name__}: {exc}"
        print(f"Sync failed: {message}", file=sys.stderr)
        await notify_sync_failed(settings.notification_urls, message)
        return True

    print(
        f"Sync complete: {len(result.downloaded)} downloaded, "
        f"{result.unchanged} unchanged, {len(result.removed)} removed, "
        f"{len(result.failed)} failed."
    )
    if not await notify_sync_complete(settings.notification_urls, result):
        print("Warning: Discord notification could not be delivered.", file=sys.stderr)
    return bool(result.failed)


async def _watch(settings: Settings) -> None:
    if settings.startup_delay:
        print(f"Waiting {settings.startup_delay}s before the first sync...")
        await asyncio.sleep(settings.startup_delay)
    print(f"Watching every {settings.poll_interval}s. Press Ctrl+C to stop.")
    while True:
        await _run_sync(settings)
        print(f"Next check in {settings.poll_interval}s.")
        await asyncio.sleep(settings.poll_interval)


async def _status(settings: Settings) -> None:
    try:
        async with ApiClient(settings.api_url, timeout=settings.timeout) as api:
            engine = SyncEngine(settings, api)
            remote_files = await engine.discover()
            plan = await engine.plan(remote_files)
    except (httpx.HTTPError, OSError, ValueError) as exc:
        print(f"Status check failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Remote files: {len(remote_files)}")
    print(f"New: {len(plan.new)}")
    print(f"Changed: {len(plan.changed)}")
    print(f"Missing locally: {len(plan.missing)}")
    print(f"Removed upstream: {len(plan.removed)}")
    print("Local mirror is current." if plan.is_current else "Local mirror needs synchronization.")


async def _list_remote(settings: Settings, limit: int) -> None:
    try:
        async with ApiClient(settings.api_url, timeout=settings.timeout) as api:
            files = await api.list_files(
                settings.root,
                search=".mp3",
                page_size=settings.page_size,
            )
    except (httpx.HTTPError, ValueError) as exc:
        print(f"Remote listing failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    visible = files if limit == 0 else files[:limit]
    for item in visible:
        print(f"{item.path}\t{item.size}")
    if len(visible) < len(files):
        print(f"… {len(files) - len(visible)} more (use --limit 0 to show all)")
    print(f"Total: {len(files)} files")


def _print_manifest(settings: Settings, as_json: bool) -> None:
    manifest = load_manifest(settings.manifest_path)
    if as_json:
        print(
            json.dumps(
                {path: entry.to_dict() for path, entry in sorted(manifest.items())},
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"Manifest: {settings.manifest_path}")
        print(f"Tracked files: {len(manifest)}")


def _settings(
    *,
    output_dir: Path | None = None,
    config_dir: Path | None = None,
    poll_interval: int | None = None,
    concurrency: int | None = None,
    cleanup: bool | None = None,
) -> Settings:
    settings = Settings.from_env()
    overrides = {
        key: value
        for key, value in {
            "output_dir": output_dir,
            "config_dir": config_dir,
            "poll_interval": poll_interval,
            "concurrency": concurrency,
            "cleanup": cleanup,
        }.items()
        if value is not None
    }
    return replace(settings, **overrides)
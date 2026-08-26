from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import httpx
import typer

from .api import ApiClient
from .config import Settings
from .manifest import load_manifest
from .notify import Notifier
from .sync import SyncEngine


app = typer.Typer(
    name="juicewrld-api-dl",
    help="Mirror the Juice WRLD API Compilation folder and keep it up to date.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


OutputOption = Annotated[
    Path | None,
    typer.Option("--out", "-o", help="Output directory. Env: JWI_OUT_DIR."),
]
ConfigOption = Annotated[
    Path | None,
    typer.Option("--config-dir", help="Manifest directory. Env: JWI_CONFIG_DIR."),
]


@app.command("sync")
def sync_command(
    output_dir: OutputOption = None,
    config_dir: ConfigOption = None,
    concurrency: Annotated[
        int | None,
        typer.Option("--concurrency", "-c", min=1, help="Parallel downloads."),
    ] = None,
    cleanup: Annotated[
        bool | None,
        typer.Option("--cleanup/--no-cleanup", help="Delete files removed upstream."),
    ] = None,
) -> None:
    """Run one synchronization pass and exit."""
    settings = _settings(
        output_dir=output_dir,
        config_dir=config_dir,
        concurrency=concurrency,
        cleanup=cleanup,
    )
    result = asyncio.run(_run_sync(settings))
    if result:
        raise typer.Exit(code=1)


@app.command("watch")
def watch_command(
    output_dir: OutputOption = None,
    config_dir: ConfigOption = None,
    interval: Annotated[
        int | None,
        typer.Option("--interval", "-i", min=60, help="Seconds between sync checks."),
    ] = None,
    concurrency: Annotated[
        int | None,
        typer.Option("--concurrency", "-c", min=1, help="Parallel downloads."),
    ] = None,
    cleanup: Annotated[
        bool | None,
        typer.Option("--cleanup/--no-cleanup", help="Delete files removed upstream."),
    ] = None,
) -> None:
    """Continuously synchronize at a fixed polling interval."""
    settings = _settings(
        output_dir=output_dir,
        config_dir=config_dir,
        poll_interval=interval,
        concurrency=concurrency,
        cleanup=cleanup,
    )
    try:
        asyncio.run(_watch(settings))
    except KeyboardInterrupt:
        typer.echo("Stopped.")


@app.command("status")
def status_command(
    output_dir: OutputOption = None,
    config_dir: ConfigOption = None,
) -> None:
    """Compare the remote collection with the local manifest without downloading."""
    settings = _settings(output_dir=output_dir, config_dir=config_dir)
    asyncio.run(_status(settings))


@app.command("list")
def list_command(
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", min=0, help="Maximum paths to print; 0 prints all."),
    ] = 50,
) -> None:
    """List files currently exposed by the remote Compilation folder."""
    settings = _settings()
    asyncio.run(_list_remote(settings, limit))


@app.command("manifest")
def manifest_command(
    config_dir: ConfigOption = None,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Print the complete manifest as JSON."),
    ] = False,
) -> None:
    """Inspect the local synchronization manifest."""
    settings = _settings(config_dir=config_dir)
    manifest = load_manifest(settings.manifest_path)
    if as_json:
        typer.echo(
            json.dumps(
                {path: entry.to_dict() for path, entry in sorted(manifest.items())},
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        typer.echo(f"Manifest: {settings.manifest_path}")
        typer.echo(f"Tracked files: {len(manifest)}")


async def _run_sync(settings: Settings) -> bool:
    notifier = Notifier(settings.notification_urls)
    try:
        async with ApiClient(settings.api_url, timeout=settings.timeout) as api:
            result = await SyncEngine(settings, api, progress=typer.echo).run()
    except (httpx.HTTPError, OSError, ValueError) as exc:
        message = f"{type(exc).__name__}: {exc}"
        typer.echo(f"Sync failed: {message}", err=True)
        await notifier.sync_failed(message)
        return True

    typer.echo(
        f"Sync complete: {len(result.downloaded)} downloaded, "
        f"{result.unchanged} unchanged, {len(result.removed)} removed, "
        f"{len(result.failed)} failed."
    )
    notification_ok = await notifier.sync_complete(result)
    if not notification_ok:
        typer.echo("Warning: one or more notifications could not be delivered.", err=True)
    return bool(result.failed)


async def _watch(settings: Settings) -> None:
    if settings.startup_delay:
        typer.echo(f"Waiting {settings.startup_delay}s before the first sync...")
        await asyncio.sleep(settings.startup_delay)
    typer.echo(f"Watching every {settings.poll_interval}s. Press Ctrl+C to stop.")
    while True:
        await _run_sync(settings)
        typer.echo(f"Next check in {settings.poll_interval}s.")
        await asyncio.sleep(settings.poll_interval)


async def _status(settings: Settings) -> None:
    try:
        async with ApiClient(settings.api_url, timeout=settings.timeout) as api:
            engine = SyncEngine(settings, api)
            remote_files = await engine.discover()
            plan = await engine.plan(remote_files)
    except (httpx.HTTPError, OSError, ValueError) as exc:
        typer.echo(f"Status check failed: {type(exc).__name__}: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Remote files: {len(remote_files)}")
    typer.echo(f"New: {len(plan.new)}")
    typer.echo(f"Changed: {len(plan.changed)}")
    typer.echo(f"Missing locally: {len(plan.missing)}")
    typer.echo(f"Removed upstream: {len(plan.removed)}")
    typer.echo("Local mirror is current." if plan.is_current else "Local mirror needs synchronization.")


async def _list_remote(settings: Settings, limit: int) -> None:
    try:
        async with ApiClient(settings.api_url, timeout=settings.timeout) as api:
            files = await api.list_files(
                settings.root,
                search=".mp3",
                page_size=settings.page_size,
            )
    except (httpx.HTTPError, ValueError) as exc:
        typer.echo(f"Remote listing failed: {type(exc).__name__}: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    visible = files if limit == 0 else files[:limit]
    for item in visible:
        typer.echo(f"{item.path}\t{item.size}")
    if len(visible) < len(files):
        typer.echo(f"… {len(files) - len(visible)} more (use --limit 0 to show all)")
    typer.echo(f"Total: {len(files)} files")


def _settings(
    *,
    output_dir: Path | None = None,
    config_dir: Path | None = None,
    poll_interval: int | None = None,
    concurrency: int | None = None,
    cleanup: bool | None = None,
) -> Settings:
    try:
        settings = Settings.from_env()
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
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


def main() -> None:
    app()
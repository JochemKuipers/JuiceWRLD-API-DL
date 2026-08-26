from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .models import DownloadResult, SyncResult


async def notify_sync_complete(
    urls: tuple[str, ...], result: SyncResult, log_file: Path | None = None
) -> bool:
    notable = [
        item for item in result.downloaded if item.status in {"new", "changed"}
    ]
    if not urls or not notable:
        return True

    new_count = sum(item.status == "new" for item in notable)
    changed_count = sum(item.status == "changed" for item in notable)
    body = (
        f"Downloaded {len(notable)} track(s): {new_count} new and "
        f"{changed_count} updated.\n\n{_format_downloads(notable)}"
    )
    return await _send(urls, "Juice WRLD compilation updated", body, log_file)


async def notify_sync_failed(
    urls: tuple[str, ...], message: str, log_file: Path | None = None
) -> bool:
    return not urls or await _send(urls, "Juice WRLD sync failed", message, log_file)


async def _send(
    urls: tuple[str, ...], title: str, body: str, log_file: Path | None = None
) -> bool:
    content = f"**{title}**\n{body}"
    if len(content) > 2000:
        content = f"{content[:1999]}…"

    kwargs: dict[str, object]
    if log_file is not None and (data := _read_log(log_file)):
        kwargs = {
            "data": {"content": content},
            "files": {"files[0]": (log_file.name, data, "text/plain")},
        }
    else:
        kwargs = {"json": {"content": content}}

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for url in urls:
                response = await client.post(_discord_webhook_url(url), **kwargs)
                response.raise_for_status()
    except (httpx.HTTPError, ValueError):
        return False
    return True


def _read_log(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


def _discord_webhook_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme == "discord" and parsed.netloc and parsed.path.strip("/"):
        return f"https://discord.com/api/webhooks/{parsed.netloc}/{parsed.path.strip('/')}"
    if (
        parsed.scheme == "https"
        and parsed.netloc in {"discord.com", "discordapp.com"}
        and parsed.path.startswith("/api/webhooks/")
    ):
        return url
    raise ValueError("JWI_NOTIFY_URLS only supports Discord webhook URLs")


def _format_downloads(items: list[DownloadResult], limit: int = 20) -> str:
    lines = [
        f"- {item.remote.path} ({_format_size(item.remote.size)})"
        for item in items[:limit]
    ]
    remaining = len(items) - limit
    if remaining > 0:
        lines.append(f"- …and {remaining} more")
    return "\n".join(lines)


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TiB"
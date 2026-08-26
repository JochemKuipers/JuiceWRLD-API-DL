from __future__ import annotations

import asyncio

import apprise

from .models import DownloadResult, SyncResult


class Notifier:
    def __init__(self, urls: tuple[str, ...]) -> None:
        self.urls = urls

    @property
    def enabled(self) -> bool:
        return bool(self.urls)

    async def sync_complete(self, result: SyncResult) -> bool:
        notable = [
            item for item in result.downloaded if item.status in {"new", "changed"}
        ]
        if not self.enabled or not notable:
            return True

        new_count = sum(item.status == "new" for item in notable)
        changed_count = sum(item.status == "changed" for item in notable)
        details = _format_downloads(notable)
        body = (
            f"Downloaded {len(notable)} track(s): {new_count} new and "
            f"{changed_count} updated.\n\n{details}"
        )
        return await self._send("Juice WRLD compilation updated", body)

    async def sync_failed(self, message: str) -> bool:
        if not self.enabled:
            return True
        return await self._send("Juice WRLD sync failed", message)

    async def _send(self, title: str, body: str) -> bool:
        def send() -> bool:
            instance = apprise.Apprise()
            if not instance.add(list(self.urls)):
                return False
            return bool(instance.notify(title=title, body=body))

        try:
            return await asyncio.to_thread(send)
        except Exception:
            # Notifications are best-effort. A provider or plugin failure must
            # not terminate the watcher after files were successfully saved.
            return False


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
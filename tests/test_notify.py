from __future__ import annotations

import httpx
import pytest
import respx

from juicewrld_api_dl.models import DownloadResult, RemoteFile, SyncResult
from juicewrld_api_dl.notify import (
    _discord_webhook_url,
    _format_downloads,
    _send,
    notify_sync_complete,
)


def result_item(index: int, status: str = "new") -> DownloadResult:
    return DownloadResult(
        remote=RemoteFile(
            path=f"Compilation/Song {index}.mp3",
            size=1024,
            modified="v1",
        ),
        status=status,
    )


def test_discord_url_is_converted_without_changing_existing_config() -> None:
    assert _discord_webhook_url("discord://123/token") == (
        "https://discord.com/api/webhooks/123/token"
    )


def test_notification_file_list_is_capped() -> None:
    body = _format_downloads([result_item(index) for index in range(25)])
    assert body.count("\n") == 20
    assert "Song 19.mp3" in body
    assert "Song 20.mp3" not in body
    assert "…and 5 more" in body


@pytest.mark.asyncio
async def test_missing_file_restoration_does_not_trigger_notification() -> None:
    result = SyncResult(
        discovered=1,
        downloaded=[result_item(1, status="missing")],
        failed=[],
        removed=[],
        unchanged=0,
    )
    assert await notify_sync_complete(("not-a-valid-url",), result) is True


@pytest.mark.asyncio
@respx.mock
async def test_discord_notification_posts_content() -> None:
    route = respx.post("https://discord.com/api/webhooks/123/token").mock(
        return_value=httpx.Response(204)
    )

    assert await _send(("discord://123/token",), "Title", "Body") is True
    assert route.calls[0].request.content == b'{"content":"**Title**\\nBody"}'


@pytest.mark.asyncio
async def test_invalid_notification_url_is_nonfatal() -> None:
    assert await _send(("https://example.test/webhook",), "Title", "Body") is False
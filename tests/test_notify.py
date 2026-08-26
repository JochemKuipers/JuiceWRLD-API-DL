from __future__ import annotations

import pytest

from juicewrld_api_dl.models import DownloadResult, RemoteFile, SyncResult
from juicewrld_api_dl.notify import Notifier, _format_downloads


def result_item(index: int, status: str = "new") -> DownloadResult:
    remote = RemoteFile(
        path=f"Compilation/Song {index}.mp3",
        name=f"Song {index}.mp3",
        size=1024,
        modified="v1",
    )
    return DownloadResult(remote=remote, status=status)


def test_notification_file_list_is_capped() -> None:
    body = _format_downloads([result_item(index) for index in range(25)])
    assert body.count("\n") == 20
    assert "Song 19.mp3" in body
    assert "Song 20.mp3" not in body
    assert "…and 5 more" in body


@pytest.mark.asyncio
async def test_missing_file_restoration_does_not_trigger_new_content_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notifier = Notifier(("json://example.test",))

    async def unexpected_send(title: str, body: str) -> bool:
        raise AssertionError(f"Unexpected notification: {title}: {body}")

    monkeypatch.setattr(notifier, "_send", unexpected_send)
    result = SyncResult(
        discovered=1,
        downloaded=[result_item(1, status="missing")],
        failed=[],
        removed=[],
        unchanged=0,
    )
    assert await notifier.sync_complete(result) is True


@pytest.mark.asyncio
async def test_notification_provider_exception_is_nonfatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notifier = Notifier(("json://example.test",))

    class BrokenApprise:
        def add(self, urls: list[str]) -> bool:
            raise RuntimeError(f"provider failed for {urls}")

    monkeypatch.setattr("juicewrld_api_dl.notify.apprise.Apprise", BrokenApprise)
    assert await notifier._send("title", "body") is False
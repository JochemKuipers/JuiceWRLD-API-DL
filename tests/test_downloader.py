from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from juicewrld_api_dl.api import ApiClient
from juicewrld_api_dl.downloader import Downloader
from juicewrld_api_dl.models import RemoteFile


def remote(size: int = 10) -> RemoteFile:
    return RemoteFile(
        path="Compilation/Song.mp3",
        size=size,
        modified="2026-01-01T00:00:00",
    )


def partial_metadata(*, etag: str = '"v1"', modified: str = "2026-01-01T00:00:00") -> str:
    return json.dumps({"size": 10, "modified": modified, "etag": etag})


@pytest.mark.asyncio
@respx.mock
async def test_download_writes_part_then_atomically_finalizes(tmp_path: Path) -> None:
    route = respx.get("https://example.test/juicewrld/files/download/").mock(
        return_value=httpx.Response(200, content=b"0123456789", headers={"ETag": '"v1"'})
    )
    destination = tmp_path / "Song.mp3"

    async with ApiClient("https://example.test/juicewrld") as api:
        etag = await Downloader(api, retries=0, retry_delay=0).download(
            remote(), destination
        )

    assert destination.read_bytes() == b"0123456789"
    assert etag == '"v1"'
    assert not destination.with_name("Song.mp3.part").exists()
    assert route.calls[0].request.url.params["path"] == "Compilation/Song.mp3"


@pytest.mark.asyncio
@respx.mock
async def test_download_resumes_partial_file_with_range_and_if_range(tmp_path: Path) -> None:
    destination = tmp_path / "Song.mp3"
    part = destination.with_name("Song.mp3.part")
    metadata = destination.with_name("Song.mp3.part.meta.json")
    part.write_bytes(b"0123")
    metadata.write_text(partial_metadata(), encoding="utf-8")

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["range"] == "bytes=4-"
        assert request.headers["if-range"] == '"v1"'
        return httpx.Response(
            206,
            content=b"456789",
            headers={"ETag": '"v1"', "Content-Range": "bytes 4-9/10"},
        )

    respx.get("https://example.test/juicewrld/files/download/").mock(side_effect=respond)
    async with ApiClient("https://example.test/juicewrld") as api:
        await Downloader(api, retries=0, retry_delay=0).download(remote(), destination)

    assert destination.read_bytes() == b"0123456789"


@pytest.mark.asyncio
@respx.mock
async def test_resume_restarts_when_etag_changes(tmp_path: Path) -> None:
    destination = tmp_path / "Song.mp3"
    destination.with_name("Song.mp3.part").write_bytes(b"0123")
    destination.with_name("Song.mp3.part.meta.json").write_text(
        partial_metadata(), encoding="utf-8"
    )

    route = respx.get("https://example.test/juicewrld/files/download/")
    route.side_effect = [
        httpx.Response(
            206,
            content=b"XXXXXX",
            headers={"ETag": '"v2"', "Content-Range": "bytes 4-9/10"},
        ),
        httpx.Response(200, content=b"abcdefghij", headers={"ETag": '"v2"'}),
    ]

    async with ApiClient("https://example.test/juicewrld") as api:
        etag = await Downloader(api, retries=1, retry_delay=0).download(
            remote(), destination
        )

    assert destination.read_bytes() == b"abcdefghij"
    assert etag == '"v2"'
    assert route.call_count == 2
    assert "range" not in route.calls[1].request.headers


@pytest.mark.asyncio
@respx.mock
async def test_stale_partial_is_discarded_instead_of_resumed(tmp_path: Path) -> None:
    destination = tmp_path / "Song.mp3"
    destination.with_name("Song.mp3.part").write_bytes(b"old partial")
    destination.with_name("Song.mp3.part.meta.json").write_text(
        partial_metadata(modified="old"), encoding="utf-8"
    )

    route = respx.get("https://example.test/juicewrld/files/download/").mock(
        return_value=httpx.Response(200, content=b"0123456789", headers={"ETag": '"v2"'})
    )
    async with ApiClient("https://example.test/juicewrld") as api:
        await Downloader(api, retries=0, retry_delay=0).download(remote(), destination)

    assert destination.read_bytes() == b"0123456789"
    assert "range" not in route.calls[0].request.headers


@pytest.mark.asyncio
@respx.mock
async def test_size_mismatch_is_resumed_on_retry(tmp_path: Path) -> None:
    destination = tmp_path / "Song.mp3"
    route = respx.get("https://example.test/juicewrld/files/download/")
    route.side_effect = [
        httpx.Response(200, content=b"0123", headers={"ETag": '"v1"'}),
        httpx.Response(
            206,
            content=b"456789",
            headers={"ETag": '"v1"', "Content-Range": "bytes 4-9/10"},
        ),
    ]

    async with ApiClient("https://example.test/juicewrld") as api:
        await Downloader(api, retries=1, retry_delay=0).download(remote(), destination)

    assert destination.read_bytes() == b"0123456789"
    assert route.calls[1].request.headers["range"] == "bytes=4-"
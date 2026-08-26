from __future__ import annotations

import httpx
import pytest
import respx

from juicewrld_api_dl.api import ApiClient


@pytest.mark.asyncio
@respx.mock
async def test_list_files_paginates_and_filters_directories() -> None:
    route = respx.get("https://example.test/juicewrld/files/browse/")
    route.side_effect = [
        httpx.Response(
            200,
            json={
                "items": [
                    {
                        "name": "A.mp3",
                        "path": "Compilation/A.mp3",
                        "type": "file",
                        "size": 10,
                        "modified": "2026-01-01T00:00:00",
                    },
                    {"name": "Folder", "path": "Compilation/Folder", "type": "directory"},
                ],
                "page": 1,
                "page_count": 2,
                "has_more": True,
            },
        ),
        httpx.Response(
            200,
            json={
                "items": [
                    {
                        "name": "B.mp3",
                        "path": "Compilation/B.mp3",
                        "type": "file",
                        "size": 20,
                        "modified": "2026-01-02T00:00:00",
                    }
                ],
                "page": 2,
                "page_count": 2,
                "has_more": False,
            },
        ),
    ]

    async with ApiClient("https://example.test/juicewrld") as api:
        files = await api.list_files("Compilation", page_size=2)

    assert [item.path for item in files] == ["Compilation/A.mp3", "Compilation/B.mp3"]
    assert route.call_count == 2
    assert route.calls[0].request.url.params["page"] == "1"
    assert route.calls[1].request.url.params["page"] == "2"


@pytest.mark.asyncio
@respx.mock
async def test_health_returns_false_on_api_error() -> None:
    respx.get("https://example.test/juicewrld/health/").mock(return_value=httpx.Response(503))
    async with ApiClient("https://example.test/juicewrld") as api:
        assert await api.health() is False
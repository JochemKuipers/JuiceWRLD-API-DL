from __future__ import annotations

import os

import httpx
import pytest

from juicewrld_api_dl.api import ApiClient
from juicewrld_api_dl.config import DEFAULT_API_URL


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("JWI_RUN_LIVE_TESTS") != "1",
        reason="Set JWI_RUN_LIVE_TESTS=1 to call the real API",
    ),
]


@pytest.mark.asyncio
async def test_live_browse_and_range_download() -> None:
    async with ApiClient(DEFAULT_API_URL, timeout=60) as api:
        files = await api.list_files("Compilation", page_size=100)
        assert len(files) > 1000
        first = min(files, key=lambda item: item.size)
        response = await api.client.get(
            "/files/download/",
            params={"path": first.path},
            headers={"Range": "bytes=0-1023"},
        )
    assert response.status_code in {httpx.codes.OK, httpx.codes.PARTIAL_CONTENT}
    assert response.headers.get("content-type", "").startswith("audio/")
    assert response.content
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from .models import RemoteFile


class ApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            headers={"User-Agent": "juicewrld-api-dl/0.1.0"},
        )

    async def __aenter__(self) -> ApiClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def health(self) -> bool:
        try:
            response = await self.client.get("/health/")
            response.raise_for_status()
            return response.json().get("status") == "ok"
        except (httpx.HTTPError, ValueError):
            return False

    async def list_files(
        self,
        root: str,
        *,
        search: str = ".mp3",
        page_size: int = 100,
    ) -> list[RemoteFile]:
        files: dict[str, RemoteFile] = {}
        page = 1
        while True:
            response = await self.client.get(
                "/files/browse/",
                params={
                    "path": root,
                    "search": search,
                    "page": page,
                    "page_size": page_size,
                },
            )
            response.raise_for_status()
            payload = response.json()
            items = payload.get("items")
            if not isinstance(items, list):
                raise ValueError("API browse response did not contain an items list")

            for raw_item in items:
                if not isinstance(raw_item, dict) or raw_item.get("type") != "file":
                    continue
                remote = RemoteFile.from_api(raw_item)
                files[remote.path] = remote

            page_count = _positive_int(payload.get("page_count"), default=page)
            has_more = bool(payload.get("has_more"))
            if not has_more or page >= page_count:
                break
            page += 1

        return [files[path] for path in sorted(files)]

    def stream_download(
        self,
        remote_path: str,
        *,
        offset: int = 0,
        etag: str = "",
    ) -> AsyncIterator[httpx.Response]:
        headers: dict[str, str] = {}
        if offset:
            headers["Range"] = f"bytes={offset}-"
            if etag:
                headers["If-Range"] = etag
        return self.client.stream(
            "GET",
            "/files/download/",
            params={"path": remote_path},
            headers=headers,
        )


def _positive_int(value: Any, *, default: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return result if result > 0 else default
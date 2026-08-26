from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from .models import RemoteFile


class ApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 120.0,
    ) -> None:
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            headers={"User-Agent": "juicewrld-api-dl"},
        )

    async def __aenter__(self) -> ApiClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self.client.aclose()

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

            page_count = int(payload.get("page_count") or page)
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
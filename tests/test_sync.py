from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import httpx
import pytest
import respx

from juicewrld_api_dl.api import ApiClient
from juicewrld_api_dl.config import Settings
from juicewrld_api_dl.manifest import load_manifest, save_manifest
from juicewrld_api_dl.models import ManifestEntry, RemoteFile
from juicewrld_api_dl.sync import SyncEngine, build_sync_plan


def item(path: str, *, size: int = 10, modified: str = "v1") -> RemoteFile:
    return RemoteFile(
        path=path,
        name=path.rsplit("/", 1)[-1],
        size=size,
        modified=modified,
    )


def test_build_sync_plan_classifies_new_changed_missing_and_removed(tmp_path: Path) -> None:
    output = tmp_path / "music"
    current = item("Compilation/current.mp3")
    changed = item("Compilation/changed.mp3", modified="v2")
    missing = item("Compilation/missing.mp3")
    new = item("Compilation/new.mp3")
    for remote in (current, changed):
        path = output / Path(remote.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"0" * remote.size)

    manifest = {
        current.path: ManifestEntry(10, "v1"),
        changed.path: ManifestEntry(10, "v1"),
        missing.path: ManifestEntry(10, "v1"),
        "Compilation/removed.mp3": ManifestEntry(10, "v1"),
    }

    plan = build_sync_plan([current, changed, missing, new], manifest, output, "Compilation")

    assert [entry.path for entry in plan.new] == [new.path]
    assert [entry.path for entry in plan.changed] == [changed.path]
    assert [entry.path for entry in plan.missing] == [missing.path]
    assert plan.removed == ["Compilation/removed.mp3"]


@pytest.mark.asyncio
@respx.mock
async def test_sync_downloads_and_updates_manifest(settings: Settings) -> None:
    browse = respx.get("https://example.test/juicewrld/files/browse/").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "name": "Song.mp3",
                        "path": "Compilation/Song.mp3",
                        "type": "file",
                        "size": 10,
                        "modified": "v1",
                    }
                ],
                "page": 1,
                "page_count": 1,
                "has_more": False,
            },
        )
    )
    download = respx.get("https://example.test/juicewrld/files/download/").mock(
        return_value=httpx.Response(200, content=b"0123456789", headers={"ETag": '"v1"'})
    )

    async with ApiClient(settings.api_url) as api:
        result = await SyncEngine(settings, api).run()

    assert browse.called and download.called
    assert len(result.downloaded) == 1
    assert not result.failed
    assert (settings.output_dir / "Compilation" / "Song.mp3").read_bytes() == b"0123456789"
    assert load_manifest(settings.manifest_path)["Compilation/Song.mp3"].etag == '"v1"'


@pytest.mark.asyncio
@respx.mock
async def test_cleanup_removes_upstream_deleted_file(settings: Settings) -> None:
    settings = replace(settings, cleanup=True)
    retained_path = settings.output_dir / "Compilation" / "Current.mp3"
    stale_path = settings.output_dir / "Compilation" / "Old.mp3"
    stale_path.parent.mkdir(parents=True)
    retained_path.write_bytes(b"current")
    stale_path.write_bytes(b"old")
    save_manifest(
        settings.manifest_path,
        {
            "Compilation/Current.mp3": ManifestEntry(7, "v1"),
            "Compilation/Old.mp3": ManifestEntry(3, "v1"),
        },
    )
    respx.get("https://example.test/juicewrld/files/browse/").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "name": "Current.mp3",
                        "path": "Compilation/Current.mp3",
                        "type": "file",
                        "size": 7,
                        "modified": "v1",
                    }
                ],
                "page": 1,
                "page_count": 1,
                "has_more": False,
            },
        )
    )

    async with ApiClient(settings.api_url) as api:
        result = await SyncEngine(settings, api).run()

    assert result.removed == ["Compilation/Old.mp3"]
    assert not stale_path.exists()
    assert load_manifest(settings.manifest_path) == {
        "Compilation/Current.mp3": ManifestEntry(7, "v1")
    }


@pytest.mark.asyncio
@respx.mock
async def test_cleanup_refuses_to_empty_an_established_mirror(settings: Settings) -> None:
    settings = replace(settings, cleanup=True)
    local_path = settings.output_dir / "Compilation" / "Old.mp3"
    local_path.parent.mkdir(parents=True)
    local_path.write_bytes(b"old")
    entry = ManifestEntry(3, "v1")
    save_manifest(settings.manifest_path, {"Compilation/Old.mp3": entry})
    respx.get("https://example.test/juicewrld/files/browse/").mock(
        return_value=httpx.Response(
            200,
            json={"items": [], "page": 1, "page_count": 1, "has_more": False},
        )
    )

    async with ApiClient(settings.api_url) as api:
        result = await SyncEngine(settings, api).run()

    assert result.removed == []
    assert local_path.read_bytes() == b"old"
    assert load_manifest(settings.manifest_path) == {"Compilation/Old.mp3": entry}
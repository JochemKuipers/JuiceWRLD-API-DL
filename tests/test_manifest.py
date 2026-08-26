from __future__ import annotations

import json
from pathlib import Path

from juicewrld_api_dl.manifest import load_manifest, save_manifest
from juicewrld_api_dl.models import ManifestEntry


def test_manifest_round_trip_is_atomic(tmp_path: Path) -> None:
    path = tmp_path / "config" / "manifest.json"
    entries = {
        "Compilation/Song.mp3": ManifestEntry(
            size=42,
            modified="2026-01-01T00:00:00",
            etag='"etag-1"',
        )
    }

    save_manifest(path, entries)

    assert load_manifest(path) == entries
    assert not path.with_name("manifest.json.tmp").exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
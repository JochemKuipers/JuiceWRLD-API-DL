from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from .models import ManifestEntry


MANIFEST_VERSION = 1


def load_manifest(path: Path) -> dict[str, ManifestEntry]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read manifest {path}: {exc}") from exc

    if not isinstance(data, dict) or data.get("version") != MANIFEST_VERSION:
        raise ValueError(f"Unsupported manifest format in {path}")
    files = data.get("files")
    if not isinstance(files, dict):
        raise ValueError(f"Manifest {path} has no valid files mapping")
    return {
        str(remote_path): ManifestEntry.from_dict(entry)
        for remote_path, entry in files.items()
        if isinstance(entry, dict)
    }


def save_manifest(path: Path, entries: dict[str, ManifestEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": MANIFEST_VERSION,
        "updated_at": datetime.now(UTC).isoformat(),
        "files": {
            remote_path: entries[remote_path].to_dict()
            for remote_path in sorted(entries)
        },
    }
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
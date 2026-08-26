from __future__ import annotations

from pathlib import Path

import pytest

from juicewrld_api_dl.paths import UnsafeRemotePathError, local_path_for


def test_local_path_preserves_compilation_tree(tmp_path: Path) -> None:
    result = local_path_for(
        tmp_path,
        "Compilation/2. Unreleased/Song.mp3",
        "Compilation",
    )
    assert result == tmp_path / "Compilation" / "2. Unreleased" / "Song.mp3"


@pytest.mark.parametrize(
    "remote_path",
    [
        "../secret.mp3",
        "Compilation/../../secret.mp3",
        "/Compilation/song.mp3",
        "Other/song.mp3",
        r"Compilation\..\secret.mp3",
    ],
)
def test_local_path_rejects_traversal(tmp_path: Path, remote_path: str) -> None:
    with pytest.raises(UnsafeRemotePathError):
        local_path_for(tmp_path, remote_path, "Compilation")
from __future__ import annotations

from pathlib import Path, PurePosixPath


class UnsafeRemotePathError(ValueError):
    pass


def local_path_for(output_dir: Path, remote_path: str, root: str) -> Path:
    """Map a safe API path beneath the configured root into output_dir.

    The root component is retained, so Compilation/foo.mp3 is written as
    <output_dir>/Compilation/foo.mp3.
    """
    normalized = remote_path.replace("\\", "/")
    path = PurePosixPath(normalized)
    root_path = PurePosixPath(root.strip("/"))
    if (
        path.is_absolute()
        or not root_path.parts
        or path.parts[: len(root_path.parts)] != root_path.parts
    ):
        raise UnsafeRemotePathError(f"Path is outside configured root {root!r}: {remote_path!r}")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafeRemotePathError(f"Unsafe path returned by API: {remote_path!r}")
    candidate = output_dir.joinpath(*path.parts)
    resolved_output = output_dir.resolve()
    resolved_candidate = candidate.resolve()
    if not resolved_candidate.is_relative_to(resolved_output):
        raise UnsafeRemotePathError(
            f"Path resolves outside output directory {output_dir}: {remote_path!r}"
        )
    return candidate
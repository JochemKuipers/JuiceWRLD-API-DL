from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RemoteFile:
    path: str
    size: int
    modified: str

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> RemoteFile:
        return cls(
            path=str(item["path"]),
            size=int(item.get("size") or 0),
            modified=str(item.get("modified") or ""),
        )


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    size: int
    modified: str
    etag: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ManifestEntry:
        return cls(
            size=int(data.get("size") or 0),
            modified=str(data.get("modified") or ""),
            etag=str(data.get("etag") or ""),
        )

    @classmethod
    def from_remote(cls, remote: RemoteFile, etag: str = "") -> ManifestEntry:
        return cls(size=remote.size, modified=remote.modified, etag=etag)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SyncPlan:
    new: list[RemoteFile]
    changed: list[RemoteFile]
    missing: list[RemoteFile]
    removed: list[str]

    @property
    def downloads(self) -> list[RemoteFile]:
        return [*self.new, *self.changed, *self.missing]

    @property
    def is_current(self) -> bool:
        return not self.downloads and not self.removed


@dataclass(slots=True)
class DownloadResult:
    remote: RemoteFile
    status: str
    etag: str = ""
    error: str = ""


@dataclass(slots=True)
class SyncResult:
    discovered: int
    downloaded: list[DownloadResult]
    failed: list[DownloadResult]
    removed: list[str]
    unchanged: int

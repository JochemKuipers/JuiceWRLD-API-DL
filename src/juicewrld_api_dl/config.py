from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_API_URL = "https://juicewrldapi.com/juicewrld"


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}, got {value}")
    return value


def _env_float(name: str, default: float, minimum: float = 0) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}, got {value}")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false, got {raw!r}")


@dataclass(frozen=True, slots=True)
class Settings:
    api_url: str
    root: str
    output_dir: Path
    config_dir: Path
    poll_interval: int
    concurrency: int
    retries: int
    retry_delay: float
    page_size: int
    timeout: float
    cleanup: bool
    notification_urls: tuple[str, ...]
    startup_delay: int

    @property
    def manifest_path(self) -> Path:
        return self.config_dir / "manifest.json"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            api_url=os.getenv("JWI_API_URL", DEFAULT_API_URL).rstrip("/"),
            root=os.getenv("JWI_ROOT", "Compilation").strip("/"),
            output_dir=Path(os.getenv("JWI_OUT_DIR", "/data")).expanduser(),
            config_dir=Path(os.getenv("JWI_CONFIG_DIR", "/config")).expanduser(),
            poll_interval=_env_int("JWI_POLL_INTERVAL", 3600, 60),
            concurrency=_env_int("JWI_CONCURRENCY", 3, 1),
            retries=_env_int("JWI_RETRIES", 5, 0),
            retry_delay=_env_float("JWI_RETRY_DELAY", 2.0, 0),
            page_size=_env_int("JWI_PAGE_SIZE", 100, 1),
            timeout=_env_float("JWI_TIMEOUT", 120.0, 1),
            cleanup=_env_bool("JWI_CLEANUP", False),
            notification_urls=tuple(
                value.strip()
                for value in os.getenv("JWI_NOTIFY_URLS", "").split(",")
                if value.strip()
            ),
            startup_delay=_env_int("JWI_STARTUP_DELAY", 0, 0),
        )
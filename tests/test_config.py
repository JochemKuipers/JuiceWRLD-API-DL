from __future__ import annotations

from pathlib import Path

import pytest

from juicewrld_api_dl.config import Settings


def test_settings_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWI_OUT_DIR", "/music")
    monkeypatch.setenv("JWI_CONFIG_DIR", "/state")
    monkeypatch.setenv("JWI_POLL_INTERVAL", "900")
    monkeypatch.setenv("JWI_CONCURRENCY", "4")
    monkeypatch.setenv("JWI_CLEANUP", "yes")
    monkeypatch.setenv("JWI_NOTIFY_URLS", "discord://one/token, discord://two/token")

    settings = Settings.from_env()

    assert settings.output_dir == Path("/music")
    assert settings.config_dir == Path("/state")
    assert settings.poll_interval == 900
    assert settings.concurrency == 4
    assert settings.cleanup is True
    assert settings.notification_urls == (
        "discord://one/token",
        "discord://two/token",
    )


def test_settings_rejects_invalid_boolean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWI_CLEANUP", "sometimes")
    with pytest.raises(ValueError, match="JWI_CLEANUP must be true or false"):
        Settings.from_env()
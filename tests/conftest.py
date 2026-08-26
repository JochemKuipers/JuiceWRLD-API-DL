from __future__ import annotations

from pathlib import Path

import pytest

from juicewrld_api_dl.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        api_url="https://example.test/juicewrld",
        root="Compilation",
        output_dir=tmp_path / "music",
        config_dir=tmp_path / "config",
        poll_interval=3600,
        concurrency=2,
        retries=1,
        retry_delay=0,
        page_size=2,
        timeout=10,
        cleanup=False,
        notification_urls=(),
        startup_delay=0,
    )
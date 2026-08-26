from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pytest

from juicewrld_api_dl.cli import (
    _configure_logging,
    _parser,
    _rotate_run_log,
)
from juicewrld_api_dl.config import Settings


@pytest.mark.parametrize("command", ["sync", "watch", "status", "list", "manifest"])
def test_all_documented_commands_parse(command: str) -> None:
    assert _parser().parse_args([command]).command == command


def test_sync_flags_preserve_cli_contract() -> None:
    args = _parser().parse_args(
        [
            "sync",
            "--out",
            "music",
            "--config-dir",
            "state",
            "--concurrency",
            "2",
            "--cleanup",
        ]
    )
    assert args.out == Path("music")
    assert args.config_dir == Path("state")
    assert args.concurrency == 2
    assert args.cleanup is True


def test_watch_rejects_too_short_poll_interval() -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args(["watch", "--interval", "59"])


def test_no_command_prints_helpful_usage(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args([])
    assert "{sync,watch,status,list,manifest}" in capsys.readouterr().err


def test_each_run_starts_a_fresh_log(settings: Settings) -> None:
    _configure_logging(settings)
    run_log = logging.getLogger("juicewrld_api_dl.cli")
    run_log.info("run one")
    _rotate_run_log()
    run_log.info("run two")

    current = settings.log_path.read_text(encoding="utf-8")
    previous = settings.config_dir / "juicewrld-api-dl.log.1"
    assert "run two" in current
    assert "run one" not in current
    assert "run one" in previous.read_text(encoding="utf-8")
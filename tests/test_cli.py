from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from juicewrld_api_dl.cli import _parser


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
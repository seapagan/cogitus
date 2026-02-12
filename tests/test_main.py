"""Tests for CLI entrypoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cogitus import main
from cogitus.cli import run_cli

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_main_runs_app(mocker: MockerFixture) -> None:
    """Main should instantiate CogitusApp and run it."""
    mocker.patch("sys.argv", ["cogitus"])
    app_cls = mocker.patch("cogitus.main.CogitusApp")
    app = app_cls.return_value

    main.main()

    app_cls.assert_called_once_with()
    app.run.assert_called_once_with()


def test_main_exits_on_cli_command(mocker: MockerFixture) -> None:
    """Main should exit with code 0 after CLI command."""
    mocker.patch("sys.argv", ["cogitus", "list"])
    mocker.patch("cogitus.cli.app")  # Mock Typer to avoid sys.exit
    mocker.patch("cogitus.main.CogitusApp")

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 0


def test_run_cli_returns_none_no_args(mocker: MockerFixture) -> None:
    """run_cli returns None when no args provided."""
    mocker.patch("sys.argv", ["cogitus"])
    assert run_cli() is None


def test_run_cli_returns_zero_with_args(mocker: MockerFixture) -> None:
    """run_cli returns 0 after running CLI command."""
    mocker.patch("sys.argv", ["cogitus", "list"])
    mock_app = mocker.patch("cogitus.cli.app")

    result = run_cli()

    mock_app.assert_called_once()
    assert result == 0

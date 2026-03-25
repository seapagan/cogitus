"""Tests for CLI entrypoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cogitus import main
from cogitus.cli import run_cli
from cogitus.db import get_db
from cogitus.metadata import AppMetadata

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
    """Main should exit when CLI command runs (Typer calls sys.exit)."""
    mocker.patch("sys.argv", ["cogitus", "list"])
    mocker.patch("cogitus.main.CogitusApp")
    mocker.patch(
        "cogitus.cli.commands.get_db",
        return_value=get_db(memory=True),
    )

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 0


def test_main_exits_on_version_command(mocker: MockerFixture) -> None:
    """Main should exit before creating the TUI for --version."""
    mocker.patch("sys.argv", ["cogitus", "--version"])
    app_cls = mocker.patch("cogitus.main.CogitusApp")
    mocker.patch(
        "cogitus.cli.commands.get_app_metadata",
        return_value=AppMetadata(
            title="Cogitus",
            version="1.2.3",
            summary="Test summary",
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 0
    app_cls.assert_not_called()


def test_run_cli_returns_for_tui(mocker: MockerFixture) -> None:
    """run_cli returns when no args provided (signals TUI launch)."""
    mocker.patch("sys.argv", ["cogitus"])
    # Should return without raising
    run_cli()


def test_run_cli_calls_app_with_args(mocker: MockerFixture) -> None:
    """run_cli calls the Typer app when args are provided."""
    mocker.patch("sys.argv", ["cogitus", "list"])
    mock_app = mocker.patch("cogitus.cli.app")

    run_cli()

    mock_app.assert_called_once()

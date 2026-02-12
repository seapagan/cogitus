"""Tests for CLI entrypoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus import main

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

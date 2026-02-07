"""Tests for CLI entrypoint."""

from __future__ import annotations

from cogitus import main


def test_main_runs_app(mocker) -> None:
    """Main should instantiate CogitusApp and run it."""
    app_cls = mocker.patch("cogitus.main.CogitusApp")
    app = app_cls.return_value

    main.main()

    app_cls.assert_called_once_with()
    app.run.assert_called_once_with()

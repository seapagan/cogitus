"""Shared test helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import App
    from textual.widget import Widget


def _focused_widget(app: App[None]) -> Widget | None:
    """Return a fresh focus snapshot for assertions.

    Tests use this helper instead of repeatedly asserting on `app.focused`
    directly because newer mypy releases can over-narrow that property across
    multiple identity checks within the same control-flow path.
    """
    return app.focused

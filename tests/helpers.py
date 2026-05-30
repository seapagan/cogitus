"""Shared test helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.models.group import Group

if TYPE_CHECKING:
    from textual.app import App
    from textual.widget import Widget


DEEP_GROUP_DEPTH = 1_100


def deep_group_chain(depth: int = DEEP_GROUP_DEPTH) -> list[Group]:
    """Build a parent-child group chain deeper than Python recursion limits."""
    return [
        Group(
            pk=index,
            created_at=index,
            updated_at=index,
            name=f"group-{index}",
            parent_pk=index - 1 if index > 1 else None,
        )
        for index in range(1, depth + 1)
    ]


def _focused_widget(app: App[None]) -> Widget | None:
    """Return a fresh focus snapshot for assertions.

    Tests use this helper instead of repeatedly asserting on `app.focused`
    directly because newer mypy releases can over-narrow that property across
    multiple identity checks within the same control-flow path.
    """
    return app.focused

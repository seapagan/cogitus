"""Persisted cursor state for idea body editing."""

from __future__ import annotations

from typing import ClassVar

from sqliter.orm import BaseDBModel, ForeignKey

from cogitus.models.idea import Idea


class IdeaCursorState(BaseDBModel):
    """Stores the last known body cursor position for an idea."""

    idea: ForeignKey[Idea] = ForeignKey(
        Idea,
        related_name="cursor_states",
        on_delete="CASCADE",
    )
    body_cursor_position: int = 0

    class Meta:
        """Metadata for the IdeaCursorState model."""

        table_name = "idea_cursor_states"
        indexes: ClassVar[list[str]] = ["idea_id"]

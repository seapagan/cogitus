"""Persisted local scroll state for rendered idea views."""

from __future__ import annotations

from typing import ClassVar

from sqliter.orm import BaseDBModel, ForeignKey

from cogitus.models.idea import Idea


class IdeaScrollState(BaseDBModel):
    """Stores the local rendered-pane scroll position for an idea."""

    idea: ForeignKey[Idea] = ForeignKey(
        Idea,
        related_name="scroll_states",
        on_delete="CASCADE",
    )
    detail_hash: str = ""
    scroll_y: int = 0

    class Meta:
        """Metadata for the IdeaScrollState model."""

        table_name = "idea_scroll_states"
        indexes: ClassVar[list[str]] = ["idea_id"]

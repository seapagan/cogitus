"""Repository for local rendered idea scroll positions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.models.idea import Idea
from cogitus.models.idea_scroll_state import IdeaScrollState

if TYPE_CHECKING:
    from sqliter import SqliterDB


class IdeaScrollStateRepository:
    """Handles local persistence of rendered-pane scroll positions."""

    def __init__(self, db: SqliterDB) -> None:
        """Initialize with a database connection."""
        self._db = db

    def get_position(self, idea_pk: int, detail_hash: str) -> int | None:
        """Return saved scroll position for an unchanged idea detail view."""
        state = (
            self._db.select(IdeaScrollState)
            .filter(idea_id=idea_pk)
            .order("updated_at", reverse=True)
            .fetch_one()
        )
        if state is None or state.detail_hash != detail_hash:
            return None
        return max(0, state.scroll_y)

    def set_position(
        self,
        idea_pk: int,
        detail_hash: str,
        scroll_y: int,
    ) -> None:
        """Create or update saved scroll position for an idea."""
        idea = self._db.get(Idea, idea_pk)
        if idea is None:
            return

        clamped_scroll_y = max(0, scroll_y)
        existing = (
            self._db.select(IdeaScrollState)
            .filter(idea_id=idea_pk)
            .order("updated_at", reverse=True)
            .fetch_one()
        )
        if existing is None:
            self._db.insert(
                IdeaScrollState(
                    idea=idea,
                    detail_hash=detail_hash,
                    scroll_y=clamped_scroll_y,
                )
            )
            return

        existing.detail_hash = detail_hash
        existing.scroll_y = clamped_scroll_y
        self._db.update(existing)

    def list_positions(self) -> dict[int, tuple[str, int]]:
        """Return the latest saved scroll position for each idea."""
        states = (
            self._db.select(IdeaScrollState).order("updated_at").fetch_all()
        )
        positions: dict[int, tuple[str, int]] = {}
        for state in states:
            idea_id = state.idea_id
            if not isinstance(idea_id, int):
                msg = "Expected IdeaScrollState.idea_id to be an int"
                raise TypeError(msg)
            positions[idea_id] = (state.detail_hash, max(0, state.scroll_y))
        return positions

    def delete_for_idea(self, idea_pk: int) -> None:
        """Delete persisted scroll positions for an idea."""
        states = (
            self._db.select(IdeaScrollState).filter(idea_id=idea_pk).fetch_all()
        )
        for state in states:
            self._db.delete(IdeaScrollState, state.pk)

"""Repository for persisted idea edit cursor positions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.models.idea import Idea
from cogitus.models.idea_cursor_state import IdeaCursorState

if TYPE_CHECKING:
    from sqliter import SqliterDB


class IdeaCursorStateRepository:
    """Handles persistence of per-idea cursor positions."""

    def __init__(self, db: SqliterDB) -> None:
        """Initialize with a database connection."""
        self._db = db

    def get_position(self, idea_pk: int) -> int | None:
        """Return saved body cursor position for an idea."""
        state = (
            self._db.select(IdeaCursorState)
            .filter(idea_id=idea_pk)
            .order("updated_at", reverse=True)
            .fetch_one()
        )
        return None if state is None else max(0, state.body_cursor_position)

    def set_position(self, idea_pk: int, position: int) -> None:
        """Create or update saved body cursor position for an idea."""
        idea = self._db.get(Idea, idea_pk)
        if idea is None:
            return

        clamped_position = max(0, position)
        existing = (
            self._db.select(IdeaCursorState).filter(idea_id=idea_pk).fetch_one()
        )
        if existing is None:
            self._db.insert(
                IdeaCursorState(
                    idea=idea,
                    body_cursor_position=clamped_position,
                )
            )
            return

        existing.body_cursor_position = clamped_position
        self._db.update(existing)

    def delete_for_idea(self, idea_pk: int) -> None:
        """Delete persisted cursor positions for an idea."""
        states = (
            self._db.select(IdeaCursorState).filter(idea_id=idea_pk).fetch_all()
        )
        for state in states:
            self._db.delete(IdeaCursorState, state.pk)

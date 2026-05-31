"""Repository for the API-visible dataset hash."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.hashing import dataset_hash
from cogitus.models.dataset_state import DatasetState
from cogitus.models.group import Group
from cogitus.models.idea import Idea
from cogitus.models.tag import Tag

if TYPE_CHECKING:
    from sqliter import SqliterDB


class DatasetStateRepository:
    """Persist and maintain a singleton dataset hash."""

    def __init__(self, db: SqliterDB) -> None:
        """Initialize with a database connection."""
        self._db = db

    def get_hash(self) -> str:
        """Return the deterministic hash for the current dataset."""
        state = self._state()
        computed = self.compute_hash()
        if state.dataset_hash != computed:
            state.dataset_hash = computed
            self._db.update(state)
        return computed

    def set_hash(self, value: str) -> None:
        """Persist an explicit dataset hash value."""
        state = self._state()
        state.dataset_hash = value
        self._db.update(state)

    def invalidate(self) -> str:
        """Recompute and persist the current deterministic dataset hash."""
        return self.get_hash()

    def compute_hash(self) -> str:
        """Compute one stable dataset hash from current API-visible rows."""
        group_parts = [
            f"group:{group.pk}:{group.created_at}:{group.updated_at}:"
            f"{group.name}:{group.parent_pk}"
            for group in self._db.select(Group).fetch_all()
        ]
        tag_parts = [
            f"tag:{tag.pk}:{tag.created_at}:{tag.updated_at}:{tag.name}"
            for tag in self._db.select(Tag).fetch_all()
        ]
        idea_parts = [
            f"idea:{idea.pk}:{idea.detail_hash}"
            for idea in self._db.select(Idea).fetch_all()
        ]
        return dataset_hash([*group_parts, *tag_parts, *idea_parts])

    def _state(self) -> DatasetState:
        """Return the singleton state row, inserting it when needed."""
        state = self._db.select(DatasetState).fetch_one()
        if state is not None:
            return state
        return self._db.insert(DatasetState())

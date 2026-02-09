"""Repository for Group CRUD operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqliter.exceptions import RecordInsertionError

from cogitus.models.group import Group

if TYPE_CHECKING:
    from sqliter import SqliterDB


class GroupRepository:
    """Handles Group persistence through sqliter-py."""

    def __init__(self, db: SqliterDB) -> None:
        """Initialize with a database connection."""
        self._db = db

    def create(self, name: str) -> Group:
        """Create and return a new group."""
        normalized = name.strip()
        if not normalized:
            msg = "Group name cannot be empty"
            raise ValueError(msg)
        try:
            return self._db.insert(Group(name=normalized))
        except RecordInsertionError as exc:
            msg = f'Group "{normalized}" already exists'
            raise ValueError(msg) from exc

    def get(self, pk: int) -> Group | None:
        """Return a group by primary key."""
        return self._db.get(Group, pk)

    def find_by_name(self, name: str) -> Group | None:
        """Find a group by exact name."""
        return self._db.select(Group).filter(name=name.strip()).fetch_one()

    def get_or_create(self, name: str) -> Group:
        """Find or create a group by name."""
        normalized = name.strip()
        found = self.find_by_name(normalized)
        if found is not None:
            return found
        try:
            return self.create(normalized)
        except ValueError:
            # Race condition: created between lookup and insert.
            found = self.find_by_name(normalized)
            if found is not None:
                return found
            raise

    def list_all(self) -> list[Group]:
        """Return all groups."""
        return self._db.select(Group).order("name").fetch_all()

    def delete(self, pk: int) -> None:
        """Delete a group by primary key."""
        self._db.delete(Group, pk)

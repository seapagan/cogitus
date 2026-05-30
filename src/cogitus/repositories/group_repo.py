"""Repository for Group CRUD operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqliter.exceptions import RecordInsertionError, RecordUpdateError

from cogitus.models.group import Group

if TYPE_CHECKING:
    from sqliter import SqliterDB


class GroupRepository:
    """Handles Group persistence through sqliter-py."""

    def __init__(self, db: SqliterDB) -> None:
        """Initialize with a database connection."""
        self._db = db

    def create(self, name: str, parent_pk: int | None = None) -> Group:
        """Create and return a new group."""
        normalized = name.strip().lower()
        if not normalized:
            msg = "Group name cannot be empty"
            raise ValueError(msg)
        if parent_pk is not None and self.get(parent_pk) is None:
            msg = "Parent group not found"
            raise ValueError(msg)
        try:
            return self._db.insert(Group(name=normalized, parent_pk=parent_pk))
        except RecordInsertionError as exc:
            msg = f'Group "{normalized}" already exists'
            raise ValueError(msg) from exc

    def get(self, pk: int) -> Group | None:
        """Return a group by primary key."""
        return self._db.get(Group, pk)

    def rename(self, pk: int, name: str) -> Group | None:
        """Rename an existing group."""
        group = self.get(pk)
        if group is None:
            return None

        normalized = name.strip().lower()
        if not normalized:
            msg = "Group name cannot be empty"
            raise ValueError(msg)

        existing = self.find_by_name(normalized)
        if existing is not None and existing.pk != pk:
            msg = f'Group "{normalized}" already exists'
            raise ValueError(msg)

        group.name = normalized
        try:
            self._db.update(group)
        except RecordUpdateError as exc:
            existing = self.find_by_name(normalized)
            if existing is not None and existing.pk != pk:
                msg = f'Group "{normalized}" already exists'
                raise ValueError(msg) from exc
            raise
        return group

    def find_by_name(self, name: str) -> Group | None:
        """Find a group by exact name."""
        normalized = name.strip().lower()
        return self._db.select(Group).filter(name=normalized).fetch_one()

    def get_or_create(self, name: str) -> Group:
        """Find or create a group by name."""
        normalized = name.strip().lower()
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

    def has_children(self, pk: int) -> bool:
        """Return whether the group has child groups."""
        return (
            self._db.select(Group).filter(parent_pk=pk).fetch_one() is not None
        )

    def descendant_pks(self, root_pk: int) -> set[int]:
        """Return the root group pk and all descendant group pks."""
        if self.get(root_pk) is None:
            return set()

        children_by_parent: dict[int, list[int]] = {}
        for group in self.list_all():
            if group.parent_pk is not None:
                children_by_parent.setdefault(group.parent_pk, []).append(
                    group.pk
                )

        descendants: set[int] = set()
        pending = [root_pk]
        while pending:
            group_pk = pending.pop()
            if group_pk in descendants:
                continue
            descendants.add(group_pk)
            pending.extend(children_by_parent.get(group_pk, []))
        return descendants

    def update_parent(self, pk: int, parent_pk: int | None) -> Group | None:
        """Update a group's parent pointer after validating the hierarchy."""
        group = self.get(pk)
        if group is None:
            return None
        if parent_pk == pk:
            msg = "Group cannot be its own parent"
            raise ValueError(msg)
        if parent_pk is not None and self.get(parent_pk) is None:
            msg = "Parent group not found"
            raise ValueError(msg)
        if parent_pk is not None and self._would_create_cycle(pk, parent_pk):
            msg = "Group parent would create a cycle"
            raise ValueError(msg)

        group.parent_pk = parent_pk
        self._db.update(group)
        return group

    def delete(self, pk: int) -> None:
        """Delete a group by primary key."""
        self._db.delete(Group, pk)

    def _would_create_cycle(self, group_pk: int, parent_pk: int) -> bool:
        """Return whether parent_pk is inside group_pk's descendant chain."""
        seen: set[int] = set()
        current_pk: int | None = parent_pk
        while current_pk is not None:
            if current_pk == group_pk:
                return True
            if current_pk in seen:
                return True
            seen.add(current_pk)
            current = self.get(current_pk)
            current_pk = None if current is None else current.parent_pk
        return False

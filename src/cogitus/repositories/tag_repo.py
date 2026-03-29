"""Repository for Tag CRUD operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sqliter.exceptions import RecordInsertionError, RecordUpdateError

from cogitus.models.idea import Idea
from cogitus.models.tag import Tag

if TYPE_CHECKING:
    from typing import Protocol

    from sqliter import SqliterDB

    class SupportsM2MRelatedName(Protocol):
        """Descriptor protocol exposing the configured reverse name."""

        related_name: str | None

    class SupportsTagUsageCountQuery(Protocol):
        """QueryBuilder surface used by list_with_usage()."""

        def with_count(
            self,
            path: str,
            alias: str = "count",
        ) -> SupportsTagUsageCountQuery:
            """Add a relationship count projection."""

        def order(
            self,
            order_by_field: str | None = None,
        ) -> SupportsTagUsageCountQuery:
            """Apply ordering to the query."""

        def fetch_dicts(self) -> list[dict[str, object]]:
            """Fetch projection query results as dictionaries."""


def _idea_tags_related_name() -> str:
    """Return the reverse relation name for Idea.tags."""
    descriptor = cast("SupportsM2MRelatedName", Idea.tags)
    related_name = descriptor.related_name
    if related_name is None:
        msg = "Idea.tags related_name is unavailable."
        raise RuntimeError(msg)
    return related_name


class TagRepository:
    """Handles Tag persistence through sqliter-py."""

    def __init__(self, db: SqliterDB) -> None:
        """Initialize with a database connection.

        Args:
            db: The SqliterDB instance.
        """
        self._db = db
        self._idea_tags_related_name = _idea_tags_related_name()

    def create(self, name: str) -> Tag:
        """Create and return a new tag."""
        normalized = name.strip().lower()
        if not normalized:
            msg = "Tag name cannot be empty"
            raise ValueError(msg)
        try:
            return self._db.insert(Tag(name=normalized))
        except RecordInsertionError as exc:
            msg = f'Tag "{normalized}" already exists'
            raise ValueError(msg) from exc

    def get(self, pk: int) -> Tag | None:
        """Return a tag by primary key."""
        return self._db.get(Tag, pk)

    def get_or_create(self, name: str) -> Tag:
        """Find an existing tag by name or create a new one.

        The name is normalized (lowered, stripped) before lookup/insert.

        Args:
            name: The tag name to find or create.

        Returns:
            The existing or newly created Tag.
        """
        normalized = name.strip().lower()
        existing = self.find_by_name(normalized)
        if existing is not None:
            return existing
        try:
            return self.create(normalized)
        except ValueError:
            # Race condition: created between check and insert
            found = self.find_by_name(normalized)
            if found is not None:
                return found
            raise  # pragma: no cover

    def find_by_name(self, name: str) -> Tag | None:
        """Find a tag by exact name match.

        Args:
            name: The tag name to search for.

        Returns:
            The matching Tag or None.
        """
        return (
            self._db.select(Tag).filter(name=name.strip().lower()).fetch_one()
        )

    def list_all(self) -> list[Tag]:
        """Return all tags sorted by name.

        Returns:
            List of all tags ordered alphabetically.
        """
        return self._db.select(Tag).order("name").fetch_all()

    def rename(self, pk: int, name: str) -> Tag | None:
        """Rename an existing tag."""
        tag = self.get(pk)
        if tag is None:
            return None

        normalized = name.strip().lower()
        if not normalized:
            msg = "Tag name cannot be empty"
            raise ValueError(msg)

        existing = self.find_by_name(normalized)
        if existing is not None and existing.pk != pk:
            msg = f'Tag "{normalized}" already exists'
            raise ValueError(msg)

        tag.name = normalized
        try:
            self._db.update(tag)
        except RecordUpdateError as exc:
            existing = self.find_by_name(normalized)
            if existing is not None and existing.pk != pk:
                msg = f'Tag "{normalized}" already exists'
                raise ValueError(msg) from exc
            raise
        return tag

    def delete(self, pk: int) -> None:
        """Delete a tag by primary key."""
        self._db.delete(Tag, pk)

    def list_in_use(self) -> list[Tag]:
        """Return tags currently linked to at least one idea.

        Returns:
            List of linked tags ordered alphabetically.
        """
        return [tag for tag, usage in self.list_with_usage() if usage > 0]

    def list_with_usage(self) -> list[tuple[Tag, int]]:
        """Return all tags and their linked-idea counts.

        Returns:
            List of (tag, usage_count) tuples ordered by tag name.
        """
        query = cast(
            "SupportsTagUsageCountQuery",
            self._db.select(Tag),
        )
        rows = (
            query.with_count(
                self._idea_tags_related_name,
                alias="usage",
            )
            .order("name")
            .fetch_dicts()
        )

        def require_mapped_value(row: dict[str, object], key: str) -> object:
            """Return a projected field value or raise a clear key error."""
            if key not in row:
                msg = f"Missing projected field: {key}"
                raise KeyError(msg)
            return row[key]

        def mapped_int(row: dict[str, object], key: str) -> int:
            """Extract an integer-compatible mapped value."""
            value = require_mapped_value(row, key)
            if isinstance(value, bool) or not isinstance(value, (int, str)):
                msg = (
                    f"Expected int or str for {key}, got {type(value).__name__}"
                )
                raise TypeError(msg)
            try:
                return int(value)
            except ValueError as exc:
                msg = f"Expected int-compatible value for {key}, got {value!r}"
                raise TypeError(msg) from exc

        def mapped_str(row: dict[str, object], key: str) -> str:
            """Extract a string-compatible mapped value."""
            value = require_mapped_value(row, key)
            if not isinstance(value, str):
                msg = f"Expected str for {key}, got {type(value).__name__}"
                raise TypeError(msg)
            return value

        return [
            (
                Tag(
                    pk=mapped_int(row, "pk"),
                    name=mapped_str(row, "name"),
                    created_at=mapped_int(row, "created_at"),
                    updated_at=mapped_int(row, "updated_at"),
                ),
                mapped_int(row, "usage"),
            )
            for row in rows
        ]

"""Repository for Tag CRUD operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sqliter.exceptions import RecordInsertionError

from cogitus.models.idea import Idea
from cogitus.models.tag import Tag

if TYPE_CHECKING:
    from typing import Protocol

    from sqliter import SqliterDB
    from sqliter.query.query import FilterValue

    class M2MSQLMetadata(Protocol):
        """Typing surface used from sqliter's public M2M SQL metadata."""

        junction_table: str
        from_column: str
        to_column: str
        source_table: str
        target_table: str
        symmetrical: bool

    class SupportsM2MSQLMetadata(Protocol):
        """Descriptor protocol exposing SQL metadata for an M2M relation."""

        @property
        def sql_metadata(self) -> M2MSQLMetadata | None:
            """Return SQL metadata for the relationship, if available."""

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


def _idea_tags_sql_metadata() -> M2MSQLMetadata:
    """Return resolved SQL metadata for the Idea.tags relationship."""
    descriptor = cast("SupportsM2MSQLMetadata", Idea.tags)
    metadata = descriptor.sql_metadata
    if metadata is None:
        msg = "Idea.tags SQL metadata is unavailable."
        raise RuntimeError(msg)
    return metadata


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
        self._idea_tags_metadata = _idea_tags_sql_metadata()
        self._idea_tags_related_name = _idea_tags_related_name()

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
            return self._db.insert(Tag(name=normalized))
        except RecordInsertionError:
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

    def list_in_use(self) -> list[Tag]:
        """Return tags currently linked to at least one idea.

        Returns:
            List of linked tags ordered alphabetically.
        """
        # SQL is assembled from trusted relationship metadata, not user input.
        meta = self._idea_tags_metadata
        query = (
            "SELECT DISTINCT "  # noqa: S608
            f'"{meta.to_column}" '
            "FROM "
            f'"{meta.junction_table}";'
        )
        rows = self._db.connect().execute(query)
        tag_pks: list[int] = [int(row[0]) for row in rows.fetchall()]
        if not tag_pks:
            return []
        # sqliter's FilterValue uses an invariant list union for __in values.
        pk_filter = cast("FilterValue", tag_pks)
        return (
            self._db.select(Tag)
            .filter(pk__in=pk_filter)
            .order("name")
            .fetch_all()
        )

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

        def mapped_int(row: dict[str, object], key: str) -> int:
            """Extract an integer-compatible mapped value."""
            if key not in row:
                msg = f"Missing projected field: {key}"
                raise KeyError(msg)
            value = row[key]
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
            if key not in row:
                msg = f"Missing projected field: {key}"
                raise KeyError(msg)
            value = row[key]
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

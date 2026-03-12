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


def _idea_tags_sql_metadata() -> M2MSQLMetadata:
    """Return resolved SQL metadata for the Idea.tags relationship."""
    descriptor = cast("SupportsM2MSQLMetadata", Idea.tags)
    metadata = descriptor.sql_metadata
    if metadata is None:
        msg = "Idea.tags SQL metadata is unavailable."
        raise RuntimeError(msg)
    return metadata


class TagRepository:
    """Handles Tag persistence through sqliter-py."""

    def __init__(self, db: SqliterDB) -> None:
        """Initialize with a database connection.

        Args:
            db: The SqliterDB instance.
        """
        self._db = db
        self._idea_tags_metadata = _idea_tags_sql_metadata()

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
        query = (
            "SELECT DISTINCT "  # noqa: S608
            f'"{self._idea_tags_metadata.to_column}" '
            "FROM "
            f'"{self._idea_tags_metadata.junction_table}";'
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
        # SQL is assembled from trusted relationship metadata, not user input.
        query = (
            "SELECT t.pk AS pk, "  # noqa: S608
            "t.name AS name, "
            "t.created_at AS created_at, "
            "t.updated_at AS updated_at, "
            f'COUNT(j."{self._idea_tags_metadata.from_column}") AS usage '
            f'FROM "{self._idea_tags_metadata.target_table}" AS t '
            f'LEFT JOIN "{self._idea_tags_metadata.junction_table}" AS j '
            f'ON j."{self._idea_tags_metadata.to_column}" = t.pk '
            "GROUP BY t.pk, t.name, t.created_at, t.updated_at "
            "ORDER BY t.name;"
        )
        cursor = self._db.connect().execute(query)
        column_names = tuple(
            description[0] for description in cursor.description or ()
        )

        def row_to_mapping(row: tuple[object, ...]) -> dict[str, object]:
            """Map sqlite row values by selected column name."""
            return dict(zip(column_names, row, strict=False))

        def mapped_int(mapping: dict[str, object], key: str) -> int:
            """Extract an integer-compatible mapped value."""
            return int(cast("int | str", mapping[key]))

        def mapped_str(mapping: dict[str, object], key: str) -> str:
            """Extract a string-compatible mapped value."""
            return str(cast("str | int", mapping[key]))

        return [
            (
                Tag(
                    pk=mapped_int(mapped, "pk"),
                    name=mapped_str(mapped, "name"),
                    created_at=mapped_int(mapped, "created_at"),
                    updated_at=mapped_int(mapped, "updated_at"),
                ),
                mapped_int(mapped, "usage"),
            )
            for mapped in (row_to_mapping(row) for row in cursor.fetchall())
        ]

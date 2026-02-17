"""Repository for Tag CRUD operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sqliter.exceptions import RecordInsertionError

from cogitus.models.tag import Tag

if TYPE_CHECKING:
    from sqliter import SqliterDB
    from sqliter.query.query import FilterValue


class TagRepository:
    """Handles Tag persistence through sqliter-py."""

    def __init__(self, db: SqliterDB) -> None:
        """Initialize with a database connection.

        Args:
            db: The SqliterDB instance.
        """
        self._db = db

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
        rows = self._db.connect().execute(
            "SELECT DISTINCT tags_pk FROM ideas_tags;"
        )
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
        rows = self._db.connect().execute(
            "SELECT tags.pk, tags.name, tags.created_at, tags.updated_at, "
            "COUNT(ideas_tags.ideas_pk) AS usage "
            "FROM tags "
            "LEFT JOIN ideas_tags ON ideas_tags.tags_pk = tags.pk "
            "GROUP BY tags.pk, tags.name, tags.created_at, tags.updated_at "
            "ORDER BY tags.name;"
        )
        return [
            (
                Tag(
                    pk=int(row[0]),
                    name=str(row[1]),
                    created_at=int(row[2]),
                    updated_at=int(row[3]),
                ),
                int(row[4]),
            )
            for row in rows.fetchall()
        ]

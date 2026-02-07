"""Service layer orchestrating idea operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.repositories.idea_repo import IdeaRepository
from cogitus.repositories.tag_repo import TagRepository

if TYPE_CHECKING:
    from sqliter import SqliterDB

    from cogitus.models.idea import Idea
    from cogitus.models.tag import Tag


class IdeaService:
    """Orchestrates idea and tag operations.

    Owns the database instance and delegates to repositories.
    Handles tag normalization (lowercase, strip, deduplicate).
    """

    def __init__(self, db: SqliterDB) -> None:
        """Initialize with a database connection.

        Args:
            db: The SqliterDB instance.
        """
        self._db = db
        self._tag_repo = TagRepository(db)
        self._idea_repo = IdeaRepository(db, self._tag_repo)

    def create_idea(
        self,
        title: str,
        body: str = "",
        tags: list[str] | None = None,
    ) -> Idea:
        """Create a new idea with optional tags.

        Args:
            title: The idea title.
            body: The idea body text (supports markdown).
            tags: Optional tag names (will be normalized).

        Returns:
            The newly created Idea.
        """
        return self._idea_repo.create(
            title=title,
            body=body,
            tag_names=self._normalize_tags(tags),
        )

    def update_idea(
        self,
        pk: int,
        title: str,
        body: str,
        tags: list[str] | None = None,
    ) -> Idea | None:
        """Update an existing idea.

        Args:
            pk: Primary key of the idea to update.
            title: New title.
            body: New body text.
            tags: If provided, replaces all tags (normalized).

        Returns:
            The updated Idea, or None if not found.
        """
        return self._idea_repo.update(
            pk=pk,
            title=title,
            body=body,
            tag_names=self._normalize_tags(tags),
        )

    def delete_idea(self, pk: int) -> None:
        """Delete an idea by primary key.

        Args:
            pk: Primary key of the idea to delete.
        """
        self._idea_repo.delete(pk)

    def get_idea(self, pk: int) -> Idea | None:
        """Fetch a single idea.

        Args:
            pk: Primary key of the idea.

        Returns:
            The Idea or None if not found.
        """
        return self._idea_repo.get(pk)

    def list_ideas(self) -> list[Idea]:
        """List all ideas, most recently updated first.

        Returns:
            List of all ideas.
        """
        return self._idea_repo.list_all()

    def search_ideas(self, query: str) -> list[Idea]:
        """Search ideas across title, body, and tags.

        Args:
            query: Search string.

        Returns:
            Matching ideas, deduplicated and sorted by recency.
        """
        return self._idea_repo.search(query)

    def list_tags(self) -> list[Tag]:
        """List all tags alphabetically.

        Returns:
            List of all tags.
        """
        return self._tag_repo.list_all()

    @staticmethod
    def _normalize_tags(
        tags: list[str] | None,
    ) -> list[str] | None:
        """Normalize tag names: lowercase, strip, deduplicate.

        Args:
            tags: Raw tag names or None.

        Returns:
            Normalized, deduplicated tag names or None.
        """
        if tags is None:
            return None
        seen: set[str] = set()
        result: list[str] = []
        for tag in tags:
            normalized = tag.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result

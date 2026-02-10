"""Service layer orchestrating idea operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.constants import DEFAULT_GROUP_NAME as SHARED_DEFAULT_GROUP_NAME
from cogitus.repositories.group_repo import GroupRepository
from cogitus.repositories.idea_repo import IdeaRepository
from cogitus.repositories.tag_repo import TagRepository

if TYPE_CHECKING:
    from sqliter import SqliterDB

    from cogitus.models.group import Group
    from cogitus.models.idea import Idea
    from cogitus.models.tag import Tag


class IdeaService:
    """Orchestrates idea and tag operations.

    Owns the database instance and delegates to repositories.
    Handles tag normalization (lowercase, strip, deduplicate).
    """

    DEFAULT_GROUP_NAME = SHARED_DEFAULT_GROUP_NAME

    def __init__(self, db: SqliterDB) -> None:
        """Initialize with a database connection.

        Args:
            db: The SqliterDB instance.
        """
        self._db = db
        self._group_repo = GroupRepository(db)
        self._tag_repo = TagRepository(db)
        self._idea_repo = IdeaRepository(
            db,
            self._tag_repo,
            self._group_repo,
            default_group_name=self.DEFAULT_GROUP_NAME,
        )

    def create_idea(
        self,
        title: str,
        body: str = "",
        tags: list[str] | None = None,
        group_pk: int | None = None,
    ) -> Idea:
        """Create a new idea with optional tags.

        Args:
            title: The idea title.
            body: The idea body text (supports markdown).
            tags: Optional tag names (will be normalized).
            group_pk: Optional group primary key.

        Returns:
            The newly created Idea.
        """
        return self._idea_repo.create(
            title=title,
            body=body,
            tag_names=self._normalize_tags(tags),
            group_pk=group_pk,
        )

    def update_idea(
        self,
        pk: int,
        title: str,
        body: str,
        tags: list[str] | None = None,
        group_pk: int | None = None,
    ) -> Idea | None:
        """Update an existing idea.

        Args:
            pk: Primary key of the idea to update.
            title: New title.
            body: New body text.
            tags: If provided, replaces all tags (normalized).
            group_pk: Optional group primary key.

        Returns:
            The updated Idea, or None if not found.
        """
        return self._idea_repo.update(
            pk=pk,
            title=title,
            body=body,
            tag_names=self._normalize_tags(tags),
            group_pk=group_pk,
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

    def list_groups(self) -> list[Group]:
        """List all groups alphabetically."""
        return self._group_repo.list_all()

    def create_group(self, name: str) -> Group:
        """Create a new group."""
        return self._group_repo.create(name)

    def has_ideas_in_group(self, group_pk: int) -> bool:
        """Return whether the given group currently contains ideas."""
        return self._idea_repo.has_for_group(group_pk)

    def list_ideas_grouped(
        self,
        query: str | None = None,
    ) -> list[tuple[Group, list[Idea]]]:
        """List ideas grouped by group with activity-based ordering."""
        groups = self._group_repo.list_all()
        ideas = (
            self._idea_repo.search(query)
            if query is not None and query.strip()
            else self._idea_repo.list_all()
        )
        by_group: dict[int, list[Idea]] = {group.pk: [] for group in groups}
        for idea in ideas:
            by_group.setdefault(idea.group.pk, []).append(idea)

        sorted_groups = sorted(
            groups,
            key=lambda group: self._group_sort_key(
                group.updated_at,
                by_group.get(group.pk, []),
            ),
            reverse=True,
        )

        grouped: list[tuple[Group, list[Idea]]] = []
        for group in sorted_groups:
            group_ideas = by_group.get(group.pk, [])
            if query is not None and query.strip() and not group_ideas:
                continue
            grouped.append((group, group_ideas))
        return grouped

    def delete_group(
        self,
        group_pk: int,
        move_to_group_pk: int | None = None,
    ) -> None:
        """Delete a group, moving ideas if needed."""
        group = self._group_repo.get(group_pk)
        if group is None:
            return
        if group.name == self.DEFAULT_GROUP_NAME:
            msg = "Default group cannot be deleted"
            raise ValueError(msg)

        target_group = (
            self._group_repo.get_or_create(self.DEFAULT_GROUP_NAME)
            if move_to_group_pk is None
            else self._group_repo.get(move_to_group_pk)
        )
        if target_group is None:
            msg = "Target group not found"
            raise ValueError(msg)
        if target_group.pk == group_pk:
            msg = "Cannot move ideas into the same group being deleted"
            raise ValueError(msg)

        self._idea_repo.bulk_move_group(group_pk, target_group.pk)
        self._group_repo.delete(group_pk)

    @staticmethod
    def _group_sort_key(
        group_updated_at: int,
        ideas: list[Idea],
    ) -> int:
        """Sort groups by most recent idea activity, then group update."""
        if ideas:
            return max(idea.updated_at for idea in ideas)
        return group_updated_at

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

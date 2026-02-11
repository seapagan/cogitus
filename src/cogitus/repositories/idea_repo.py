"""Repository for Idea CRUD operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.constants import DEFAULT_GROUP_NAME
from cogitus.models.idea import Idea
from cogitus.models.tag import Tag

if TYPE_CHECKING:
    from sqliter import SqliterDB

    from cogitus.models.group import Group
    from cogitus.repositories.group_repo import GroupRepository
    from cogitus.repositories.tag_repo import TagRepository


class IdeaRepository:
    """Handles Idea persistence and querying through sqliter-py."""

    def __init__(
        self,
        db: SqliterDB,
        tag_repo: TagRepository,
        group_repo: GroupRepository,
        *,
        default_group_name: str = DEFAULT_GROUP_NAME,
    ) -> None:
        """Initialize with a database connection and tag repository.

        Args:
            db: The SqliterDB instance.
            tag_repo: The TagRepository for tag operations.
            group_repo: The GroupRepository for group operations.
            default_group_name: Fallback group used when group_pk is None.
        """
        self._db = db
        self._tag_repo = tag_repo
        self._group_repo = group_repo
        self._default_group_name = default_group_name

    def create(
        self,
        title: str,
        body: str = "",
        tag_names: list[str] | None = None,
        group_pk: int | None = None,
    ) -> Idea:
        """Insert a new idea with optional tags.

        Args:
            title: The idea title.
            body: The idea body text.
            tag_names: Optional list of tag names to associate.
            group_pk: Optional group primary key.

        Returns:
            The newly created Idea.
        """
        group = self._resolve_group(group_pk)
        idea = self._db.insert(Idea(title=title, body=body, group=group))
        if tag_names:
            tags = [self._tag_repo.get_or_create(n) for n in tag_names]
            idea.tags.add(*tags)
        return idea

    def get(self, pk: int) -> Idea | None:
        """Fetch a single idea by primary key.

        Args:
            pk: The primary key of the idea.

        Returns:
            The Idea or None if not found.
        """
        return self._db.get(Idea, pk)

    def list_all(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Idea]:
        """Fetch ideas ordered by most recently updated.

        Args:
            limit: Maximum number of ideas to return.
            offset: Number of ideas to skip.

        Returns:
            List of ideas sorted by updated_at descending.
        """
        return (
            self._db.select(Idea)
            .order("updated_at", reverse=True)
            .limit(limit)
            .offset(offset)
            .fetch_all()
        )

    def update(
        self,
        pk: int,
        title: str,
        body: str,
        tag_names: list[str] | None = None,
        group_pk: int | None = None,
    ) -> Idea | None:
        """Update an idea's fields and re-sync tag associations.

        Args:
            pk: The primary key of the idea to update.
            title: The new title.
            body: The new body text.
            tag_names: If provided, replace all tags with these.
            group_pk: Optional group primary key. When None, preserve the
                existing group assignment.

        Returns:
            The updated Idea, or None if not found.
        """
        idea = self._db.get(Idea, pk)
        if idea is None:
            return None

        idea.title = title
        idea.body = body
        if group_pk is not None:
            idea.group = self._resolve_group(group_pk)
        self._db.update(idea)

        if tag_names is not None:
            tags = [self._tag_repo.get_or_create(n) for n in tag_names]
            idea.tags.set(*tags)

        return idea

    def delete(self, pk: int) -> None:
        """Delete an idea by primary key.

        Junction table rows are removed via CASCADE.

        Args:
            pk: The primary key of the idea to delete.
        """
        self._db.delete(Idea, pk)

    def search(self, query: str) -> list[Idea]:
        """Search ideas across title, body, and tag names.

        Uses LIKE-based filtering. Results are deduplicated and
        sorted by updated_at descending.

        Args:
            query: The search string.

        Returns:
            List of matching ideas.
        """
        if not query.strip():
            return self.list_all()

        seen: set[int] = set()
        results: list[Idea] = []

        # Search title
        for idea in (
            self._db.select(Idea).filter(title__icontains=query).fetch_all()
        ):
            if idea.pk not in seen:
                seen.add(idea.pk)
                results.append(idea)

        # Search body
        for idea in (
            self._db.select(Idea).filter(body__icontains=query).fetch_all()
        ):
            if idea.pk not in seen:
                seen.add(idea.pk)
                results.append(idea)

        # Search via tag names
        matching_tags = (
            self._db.select(Tag).filter(name__icontains=query).fetch_all()
        )
        for tag in matching_tags:
            for idea in tag.ideas.fetch_all():  # type: ignore[attr-defined]
                if idea.pk not in seen:
                    seen.add(idea.pk)
                    results.append(idea)

        results.sort(key=lambda i: i.updated_at, reverse=True)
        return results

    def list_for_group(self, group_pk: int) -> list[Idea]:
        """Return ideas for a specific group ordered by recency."""
        return (
            self._db.select(Idea)
            .filter(group_id=group_pk)
            .order("updated_at", reverse=True)
            .fetch_all()
        )

    def has_for_group(self, group_pk: int) -> bool:
        """Return whether a group has at least one idea."""
        return (
            self._db.select(Idea).filter(group_id=group_pk).limit(1).fetch_one()
            is not None
        )

    def bulk_move_group(
        self,
        source_group_pk: int,
        target_group_pk: int,
    ) -> int:
        """Move all ideas from source group to target group."""
        target_group = self._resolve_group(target_group_pk)
        ideas = self.list_for_group(source_group_pk)
        for idea in ideas:
            idea.group = target_group
            self._db.update(idea)
        return len(ideas)

    def _resolve_group(self, group_pk: int | None) -> Group:
        """Resolve a group by primary key, falling back to default."""
        if group_pk is not None:
            group = self._group_repo.get(group_pk)
            if group is not None:
                return group
            msg = f"Group with pk={group_pk} not found"
            raise ValueError(msg)
        return self._group_repo.get_or_create(self._default_group_name)

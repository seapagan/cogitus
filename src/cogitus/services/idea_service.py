"""Service layer orchestrating idea operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cogitus.config import normalize_default_group_name
from cogitus.constants import DEFAULT_GROUP_NAME
from cogitus.repositories.group_repo import GroupRepository
from cogitus.repositories.idea_cursor_state_repo import (
    IdeaCursorStateRepository,
)
from cogitus.repositories.idea_repo import IdeaRepository
from cogitus.repositories.tag_repo import TagRepository
from cogitus.search import parse_search_query

if TYPE_CHECKING:
    from sqliter import SqliterDB

    from cogitus.models.group import Group
    from cogitus.models.idea import Idea
    from cogitus.models.tag import Tag
    from cogitus.search import SearchResult


logger = logging.getLogger(__name__)


class IdeaService:
    """Orchestrates idea and tag operations.

    Owns the database instance and delegates to repositories.
    Handles tag normalization (lowercase, strip, deduplicate).
    """

    def __init__(
        self,
        db: SqliterDB,
        *,
        default_group_name: str = DEFAULT_GROUP_NAME,
    ) -> None:
        """Initialize with a database connection.

        Args:
            db: The SqliterDB instance.
            default_group_name: Canonical fallback group name.
        """
        self._db = db
        self._default_group_name = normalize_default_group_name(
            default_group_name
        )
        self._group_repo = GroupRepository(db)
        self._tag_repo = TagRepository(db)
        self._cursor_state_repo = IdeaCursorStateRepository(db)
        self._idea_repo = IdeaRepository(
            db,
            self._tag_repo,
            self._group_repo,
            default_group_name=self._default_group_name,
        )

    @property
    def default_group_name(self) -> str:
        """Return the canonical fallback group name."""
        return self._default_group_name

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

    def rename_idea(self, pk: int, title: str) -> Idea | None:
        """Rename an existing idea without rewriting other fields.

        Args:
            pk: Primary key of the idea to rename.
            title: New title.

        Returns:
            The updated Idea, or None if not found.
        """
        try:
            return self._idea_repo.rename(pk=pk, title=title)
        except ValueError:
            raise
        except Exception as exc:
            logger.exception("Failed to rename idea pk=%s", pk)
            msg = "Failed to rename idea"
            raise ValueError(msg) from exc

    def delete_idea(self, pk: int) -> None:
        """Delete an idea by primary key.

        Args:
            pk: Primary key of the idea to delete.
        """
        self._cursor_state_repo.delete_for_idea(pk)
        self._idea_repo.delete(pk)

    def get_idea(self, pk: int) -> Idea | None:
        """Fetch a single idea.

        Args:
            pk: Primary key of the idea.

        Returns:
            The Idea or None if not found.
        """
        return self._idea_repo.get(pk)

    def get_idea_with_relations(self, pk: int) -> Idea | None:
        """Fetch one idea with group and tags eagerly loaded."""
        return self._idea_repo.get_with_relations(pk)

    def list_ideas(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Idea]:
        """List all ideas, most recently updated first.

        Returns:
            List of all ideas.
        """
        return self._idea_repo.list_all(limit=limit, offset=offset)

    def search_ideas(self, query: str) -> list[Idea]:
        """Search ideas by visible text and optional structured filters.

        Args:
            query: Search string.

        Returns:
            Matching ideas, deduplicated and sorted by recency.
        """
        return self.search_ideas_advanced(query)

    def search_ideas_advanced(self, query: str) -> list[Idea]:
        """Search ideas using parsed free-text and structured filters."""
        parsed = parse_search_query(query)
        return self._idea_repo.search_advanced(parsed)

    def search_results(self, query: str) -> list[SearchResult]:
        """Search ideas and return ranked result metadata."""
        parsed = parse_search_query(query)
        return self._idea_repo.search_results(parsed)

    def list_tags(self) -> list[Tag]:
        """List all tags alphabetically.

        Returns:
            List of all tags.
        """
        return self._tag_repo.list_all()

    def get_tag(self, pk: int) -> Tag | None:
        """Fetch a single tag by primary key."""
        return self._tag_repo.get(pk)

    def create_tag(self, name: str) -> Tag:
        """Create a standalone tag."""
        return self._tag_repo.create(name)

    def rename_tag(self, pk: int, name: str) -> Tag | None:
        """Rename an existing tag and refresh search data."""
        tag = self._tag_repo.rename(pk, name)
        if tag is not None:
            self._idea_repo.rebuild_search_index()
        return tag

    def delete_tag(self, pk: int) -> None:
        """Delete a tag and refresh search data."""
        self._tag_repo.delete(pk)
        self._idea_repo.rebuild_search_index()

    def list_tags_in_use(self) -> list[Tag]:
        """List tags currently linked to at least one idea."""
        return self._tag_repo.list_in_use()

    def list_tags_with_usage(self) -> list[tuple[Tag, int]]:
        """List all tags with their current linked-idea usage counts."""
        return self._tag_repo.list_with_usage()

    def get_idea_cursor_position(self, idea_pk: int) -> int | None:
        """Return persisted body cursor position for an idea, if present."""
        return self._cursor_state_repo.get_position(idea_pk)

    def set_idea_cursor_position(self, idea_pk: int, position: int) -> None:
        """Persist body cursor position for an idea."""
        self._cursor_state_repo.set_position(idea_pk, position)

    def list_groups(self) -> list[Group]:
        """List all groups alphabetically."""
        return self._group_repo.list_all()

    def get_group(self, pk: int) -> Group | None:
        """Fetch a single group by primary key."""
        return self._group_repo.get(pk)

    def create_group(self, name: str) -> Group:
        """Create a new group."""
        return self._group_repo.create(name)

    def rename_group(self, pk: int, name: str) -> Group | None:
        """Rename an existing group."""
        group = self._group_repo.get(pk)
        if group is None:
            return None
        if group.name == self._default_group_name:
            msg = "Default group cannot be renamed"
            raise ValueError(msg)
        try:
            renamed = self._group_repo.rename(pk, name)
            if renamed is not None:
                self._idea_repo.rebuild_search_index()
        except ValueError:
            raise
        except Exception as exc:
            logger.exception("Failed to rename group pk=%s", pk)
            msg = "Failed to rename group"
            raise ValueError(msg) from exc
        else:
            return renamed

    def has_ideas_in_group(self, group_pk: int) -> bool:
        """Return whether the given group currently contains ideas."""
        return self._idea_repo.has_for_group(group_pk)

    def list_ideas_grouped(
        self,
        query: str | None = None,
    ) -> list[tuple[Group, list[Idea]]]:
        """List ideas grouped by group with activity-based ordering."""
        groups = self._group_repo.list_all()
        query_active = self._query_has_text(query)
        ideas = self._ideas_for_query(query, query_active=query_active)
        by_group = self._group_ideas(groups, ideas)
        return self._build_grouped_result(
            groups,
            by_group,
            query_active=query_active,
        )

    def list_search_results_grouped(
        self,
        query: str,
    ) -> list[tuple[Group, list[SearchResult]]]:
        """Return ranked search results grouped by idea group."""
        groups = self._group_repo.list_all()
        results = self.search_results(query)
        by_group: dict[int, list[SearchResult]] = {
            group.pk: [] for group in groups
        }
        for result in results:
            by_group.setdefault(result.idea.group.pk, []).append(result)

        sorted_groups = sorted(
            groups,
            key=lambda group: self._group_sort_key(
                group.updated_at,
                [result.idea for result in by_group.get(group.pk, [])],
            ),
            reverse=True,
        )

        grouped: list[tuple[Group, list[SearchResult]]] = []
        for group in sorted_groups:
            group_results = by_group.get(group.pk, [])
            if not group_results:
                continue
            grouped.append((group, group_results))
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
        if group.name == self._default_group_name:
            msg = "Default group cannot be deleted"
            raise ValueError(msg)

        target_group = (
            self._group_repo.get_or_create(self._default_group_name)
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
    def _query_has_text(query: str | None) -> bool:
        """Return whether a query string is present and non-empty."""
        return query is not None and bool(query.strip())

    def _ideas_for_query(
        self,
        query: str | None,
        *,
        query_active: bool,
    ) -> list[Idea]:
        """Return ideas for grouped display based on query state."""
        if query_active:
            # query is guaranteed non-empty by query_active.
            return [result.idea for result in self.search_results(query or "")]
        return self._idea_repo.list_all()

    @staticmethod
    def _group_ideas(
        groups: list[Group],
        ideas: list[Idea],
    ) -> dict[int, list[Idea]]:
        """Map ideas by group primary key."""
        by_group: dict[int, list[Idea]] = {group.pk: [] for group in groups}
        for idea in ideas:
            by_group.setdefault(idea.group.pk, []).append(idea)
        return by_group

    def _build_grouped_result(
        self,
        groups: list[Group],
        by_group: dict[int, list[Idea]],
        *,
        query_active: bool,
    ) -> list[tuple[Group, list[Idea]]]:
        """Build sorted grouped idea tuples, filtering empty query groups."""
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
            if query_active and not group_ideas:
                continue
            grouped.append((group, group_ideas))
        return grouped

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

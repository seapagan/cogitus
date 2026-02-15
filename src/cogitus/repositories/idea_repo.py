"""Repository for Idea CRUD operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.constants import DEFAULT_GROUP_NAME
from cogitus.models.idea import Idea
from cogitus.models.tag import Tag
from cogitus.search import SearchFilter, SearchQuery, parse_search_query

if TYPE_CHECKING:
    from sqliter import SqliterDB

    from cogitus.models.group import Group
    from cogitus.repositories.group_repo import GroupRepository
    from cogitus.repositories.tag_repo import TagRepository
    from cogitus.search.query import FilterConnector


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

    def get_with_relations(self, pk: int) -> Idea | None:
        """Fetch one idea with group/tags loaded for formatter paths."""
        return (
            self._db.select(Idea)
            .select_related("group")
            .prefetch_related("tags")
            .filter(pk=pk)
            .fetch_one()
        )

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
            .select_related("group")
            .prefetch_related("tags")
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
        """Search ideas using raw query text compatibility API."""
        return self.search_advanced(parse_search_query(query))

    def search_advanced(self, query: SearchQuery) -> list[Idea]:
        """Search ideas using parsed free text and structured filters."""
        if query.text is None and not query.filters:
            return self.list_all()

        text_matches = (
            self._matching_pks_for_text(query.text)
            if query.text is not None
            else None
        )
        filter_matches = (
            self._matching_pks_for_filters(
                query.filters,
                query.connectors,
            )
            if query.filters
            else None
        )
        matched_pks = self._combine_match_sets(text_matches, filter_matches)
        if not matched_pks:
            return []
        return self._fetch_ideas_by_pk(matched_pks)

    @staticmethod
    def _combine_match_sets(
        text_matches: set[int] | None,
        filter_matches: set[int] | None,
    ) -> set[int]:
        """Combine text and structured filter matches with intersection."""
        if text_matches is None and filter_matches is None:
            return set()
        if text_matches is None:
            return set(filter_matches or set())
        if filter_matches is None:
            return set(text_matches)
        return text_matches & filter_matches

    def _matching_pks_for_text(self, text_query: str) -> set[int]:
        """Return idea primary keys matching text across title/body/tag."""
        query = text_query.strip()
        if not query:
            return set()

        matched_pks: set[int] = set()
        for idea in (
            self._db.select(Idea).filter(title__icontains=query).fetch_all()
        ):
            matched_pks.add(idea.pk)
        for idea in (
            self._db.select(Idea).filter(body__icontains=query).fetch_all()
        ):
            matched_pks.add(idea.pk)

        matching_tags = (
            self._db.select(Tag).filter(name__icontains=query).fetch_all()
        )
        for tag in matching_tags:
            for idea in tag.ideas.fetch_all():  # type: ignore[attr-defined]
                matched_pks.add(idea.pk)

        return matched_pks

    def _matching_pks_for_filters(
        self,
        filters: tuple[SearchFilter, ...],
        connectors: tuple[FilterConnector, ...],
    ) -> set[int]:
        """Evaluate structured filters left-to-right with AND/OR connectors."""
        if not filters:
            return set()

        folded = self._matching_pks_for_filter(filters[0])
        for index in range(1, len(filters)):
            connector = (
                connectors[index - 1] if index - 1 < len(connectors) else "and"
            )
            next_matches = self._matching_pks_for_filter(filters[index])
            if connector == "or":
                folded |= next_matches
            else:
                folded &= next_matches
        return folded

    def _matching_pks_for_filter(self, search_filter: SearchFilter) -> set[int]:
        """Return idea primary keys matching one structured filter."""
        if search_filter.field == "tag":
            return self._matching_pks_for_tag(search_filter.value)
        if search_filter.field == "group":
            return self._matching_pks_for_group(search_filter.value)
        msg = f"Unsupported filter field: {search_filter.field}"
        raise ValueError(msg)

    def _matching_pks_for_tag(self, tag_name: str) -> set[int]:
        """Return idea primary keys for a single exact tag name."""
        tag = self._tag_repo.find_by_name(tag_name)
        if tag is None:
            return set()
        return {idea.pk for idea in tag.ideas.fetch_all()}  # type: ignore[attr-defined]

    def _matching_pks_for_group(self, group_name: str) -> set[int]:
        """Return idea primary keys for a single exact group name."""
        group = self._group_repo.find_by_name(group_name)
        if group is None:
            return set()
        matched = self._db.select(Idea).filter(group_id=group.pk).fetch_all()
        return {idea.pk for idea in matched}

    def _fetch_ideas_by_pk(self, idea_pks: set[int]) -> list[Idea]:
        """Fetch idea models with relations for the given primary keys."""
        ideas = (
            self._db.select(Idea)
            .select_related("group")
            .prefetch_related("tags")
            .filter(pk__in=list(idea_pks))
            .fetch_all()
        )
        ideas.sort(key=lambda idea: idea.updated_at, reverse=True)
        return ideas

    def list_for_group(self, group_pk: int) -> list[Idea]:
        """Return ideas for a specific group ordered by recency."""
        return (
            self._db.select(Idea)
            .select_related("group")
            .prefetch_related("tags")
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
        """Move all ideas from source group to target group.

        Returns:
            The number of ideas that were moved.
        """
        if source_group_pk == target_group_pk:
            return 0

        # Validate target group exists
        self._resolve_group(target_group_pk)

        return self._db.update_where(
            Idea,
            where={"group_id": source_group_pk},
            values={"group_id": target_group_pk},
        )

    def _resolve_group(self, group_pk: int | None) -> Group:
        """Resolve a group by primary key, falling back to default."""
        if group_pk is not None:
            group = self._group_repo.get(group_pk)
            if group is not None:
                return group
            msg = f"Group with pk={group_pk} not found"
            raise ValueError(msg)
        return self._group_repo.get_or_create(self._default_group_name)

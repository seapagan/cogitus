"""Repository for mirroring remote API data into the local cache."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.models.group import Group
from cogitus.models.idea import Idea
from cogitus.models.idea_cursor_state import IdeaCursorState
from cogitus.models.tag import Tag
from cogitus.repositories.group_repo import GroupRepository
from cogitus.repositories.idea_cursor_state_repo import (
    IdeaCursorStateRepository,
)
from cogitus.search.backend import FtsSearchBackend

if TYPE_CHECKING:
    from sqliter import SqliterDB

    from cogitus.api.schemas.response.group import GroupResponse
    from cogitus.api.schemas.response.idea import IdeaResponse
    from cogitus.api.schemas.response.tag import TagResponse
    from cogitus.backends.types import RemoteSnapshot


class RemoteCacheRepository:
    """Persist remote API state into the local SQLite cache."""

    def __init__(
        self,
        db: SqliterDB,
        *,
        default_group_name: str,
    ) -> None:
        """Initialize the cache repository with its persistence helpers."""
        self._db = db
        self._default_group_name = default_group_name
        self._cursor_repo = IdeaCursorStateRepository(db)
        self._group_repo = GroupRepository(db)
        self._search_backend = FtsSearchBackend(db)

    def replace_snapshot(self, snapshot: RemoteSnapshot) -> None:
        """Replace the entire cache with a fresh remote snapshot."""
        cursor_positions = self._cursor_repo.list_positions()

        with self._db.connect():
            self._db.select(IdeaCursorState).delete()
            self._db.select(Idea).delete()
            self._db.select(Tag).delete()
            self._db.select(Group).delete()

            groups_by_pk = self._bulk_insert_groups(snapshot.groups)
            tags_by_pk = self._bulk_insert_tags(snapshot.tags)
            self._bulk_insert_ideas(snapshot.ideas, groups_by_pk)
            self._sync_snapshot_idea_tags(snapshot.ideas, tags_by_pk)

        self._search_backend.rebuild()
        self._restore_cursor_positions(
            cursor_positions,
            valid_idea_pks={idea.pk for idea in snapshot.ideas},
        )

    def upsert_group(self, group: GroupResponse) -> None:
        """Insert or update one cached group with remote timestamps."""
        if self._db.get(Group, group.pk) is None:
            self._db.insert(
                self._group_model(group),
                timestamp_override=True,
            )
            return

        self._db.update_where(
            Group,
            where={"pk": group.pk},
            values={
                "created_at": group.created_at,
                "updated_at": group.updated_at,
                "name": group.name,
            },
        )

    def upsert_tag(self, tag: TagResponse) -> None:
        """Insert or update one cached tag with remote timestamps."""
        if self._db.get(Tag, tag.pk) is None:
            self._db.insert(
                self._tag_model(tag),
                timestamp_override=True,
            )
            return

        self._db.update_where(
            Tag,
            where={"pk": tag.pk},
            values={
                "created_at": tag.created_at,
                "updated_at": tag.updated_at,
                "name": tag.name,
            },
        )

    def upsert_idea(self, idea: IdeaResponse) -> None:
        """Insert or update one cached idea and its tag links."""
        self.upsert_group(idea.group)
        for tag in idea.tags:
            self.upsert_tag(tag)

        cached_group = self._require_group(idea.group.pk)
        if self._db.get(Idea, idea.pk) is None:
            self._db.insert(
                self._idea_model(idea, cached_group),
                timestamp_override=True,
            )
        else:
            self._db.update_where(
                Idea,
                where={"pk": idea.pk},
                values={
                    "created_at": idea.created_at,
                    "updated_at": idea.updated_at,
                    "title": idea.title,
                    "body": idea.body,
                    "group_id": cached_group.pk,
                },
            )

        cached_idea = self._require_idea(idea.pk)
        cached_tags = [self._require_tag(tag.pk) for tag in idea.tags]
        cached_idea.tags.set(*cached_tags)
        self._search_backend.upsert_idea(idea.pk)

    def delete_idea(self, idea_pk: int) -> None:
        """Delete one cached idea and its derived search entry."""
        self._db.delete(Idea, idea_pk)
        self._search_backend.delete_idea(idea_pk)

    def delete_group(
        self,
        group_pk: int,
        *,
        move_to_group_pk: int | None,
    ) -> None:
        """Delete one cached group after moving ideas to the target group."""
        group = self._db.get(Group, group_pk)
        if group is None:
            return

        target_group_pk = self._resolve_move_target_group_pk(
            group_pk=group_pk,
            move_to_group_pk=move_to_group_pk,
        )
        self._db.update_where(
            Idea,
            where={"group_id": group_pk},
            values={"group_id": target_group_pk},
        )
        self._db.delete(Group, group_pk)
        self._search_backend.rebuild()

    def rebuild_search_index(self) -> None:
        """Rebuild the cache search index from relational tables."""
        self._search_backend.rebuild()

    def _bulk_insert_groups(
        self,
        groups: list[GroupResponse],
    ) -> dict[int, Group]:
        """Insert snapshot groups and return them keyed by primary key."""
        if not groups:
            return {}
        inserted = self._db.bulk_insert(
            [self._group_model(group) for group in groups],
            timestamp_override=True,
        )
        return {group.pk: group for group in inserted}

    def _bulk_insert_tags(
        self,
        tags: list[TagResponse],
    ) -> dict[int, Tag]:
        """Insert snapshot tags and return them keyed by primary key."""
        if not tags:
            return {}
        inserted = self._db.bulk_insert(
            [self._tag_model(tag) for tag in tags],
            timestamp_override=True,
        )
        return {tag.pk: tag for tag in inserted}

    def _bulk_insert_ideas(
        self,
        ideas: list[IdeaResponse],
        groups_by_pk: dict[int, Group],
    ) -> None:
        """Insert snapshot ideas using already-inserted cached groups."""
        if not ideas:
            return
        self._db.bulk_insert(
            [
                self._idea_model(
                    idea,
                    groups_by_pk[idea.group.pk],
                )
                for idea in ideas
            ],
            timestamp_override=True,
        )

    def _sync_snapshot_idea_tags(
        self,
        ideas: list[IdeaResponse],
        tags_by_pk: dict[int, Tag],
    ) -> None:
        """Recreate snapshot idea-tag links through the ORM M2M API."""
        for idea in ideas:
            cached_idea = self._require_idea(idea.pk)
            cached_idea.tags.set(
                *(tags_by_pk[tag.pk] for tag in idea.tags),
            )

    def _restore_cursor_positions(
        self,
        cursor_positions: dict[int, int],
        *,
        valid_idea_pks: set[int],
    ) -> None:
        """Restore cursor positions for ideas that still exist remotely."""
        for idea_pk, position in cursor_positions.items():
            if idea_pk in valid_idea_pks:
                self._cursor_repo.set_position(idea_pk, position)

    def _resolve_move_target_group_pk(
        self,
        *,
        group_pk: int,
        move_to_group_pk: int | None,
    ) -> int:
        """Resolve the destination group when mirroring a group deletion."""
        target_group = (
            self._require_group(move_to_group_pk)
            if move_to_group_pk is not None
            else self._group_repo.find_by_name(self._default_group_name)
        )
        if target_group is None:
            msg = "Default group missing from local cache"
            raise RuntimeError(msg)
        if target_group.pk == group_pk:
            msg = "Cannot move cached ideas into the group being deleted"
            raise RuntimeError(msg)
        return target_group.pk

    @staticmethod
    def _group_model(group: GroupResponse) -> Group:
        """Build a cached group model from an API response."""
        return Group(
            pk=group.pk,
            created_at=group.created_at,
            updated_at=group.updated_at,
            name=group.name,
        )

    @staticmethod
    def _tag_model(tag: TagResponse) -> Tag:
        """Build a cached tag model from an API response."""
        return Tag(
            pk=tag.pk,
            created_at=tag.created_at,
            updated_at=tag.updated_at,
            name=tag.name,
        )

    @staticmethod
    def _idea_model(
        idea: IdeaResponse,
        group: Group,
    ) -> Idea:
        """Build a cached idea model from an API response."""
        return Idea(
            pk=idea.pk,
            created_at=idea.created_at,
            updated_at=idea.updated_at,
            title=idea.title,
            body=idea.body,
            group=group,
        )

    def _require_group(self, group_pk: int) -> Group:
        """Return a cached group or raise a clear runtime error."""
        group = self._db.get(Group, group_pk)
        if group is None:
            msg = f"Group {group_pk} not found in local cache"
            raise RuntimeError(msg)
        return group

    def _require_tag(self, tag_pk: int) -> Tag:
        """Return a cached tag or raise a clear runtime error."""
        tag = self._db.get(Tag, tag_pk)
        if tag is None:
            msg = f"Tag {tag_pk} not found in local cache"
            raise RuntimeError(msg)
        return tag

    def _require_idea(self, idea_pk: int) -> Idea:
        """Return a cached idea or raise a clear runtime error."""
        idea = self._db.get(Idea, idea_pk)
        if idea is None:
            msg = f"Idea {idea_pk} not found in local cache"
            raise RuntimeError(msg)
        return idea

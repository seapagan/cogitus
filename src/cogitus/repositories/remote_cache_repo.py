"""Repository for mirroring remote API data into the local cache."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.models.group import Group
from cogitus.models.idea import Idea
from cogitus.models.tag import Tag
from cogitus.repositories.dataset_state_repo import DatasetStateRepository
from cogitus.repositories.group_repo import GroupRepository
from cogitus.repositories.snapshot_import_repo import SnapshotImportRepository
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
        self._group_repo = GroupRepository(db)
        self._dataset_state_repo = DatasetStateRepository(db)
        self._snapshot_importer = SnapshotImportRepository(db)
        self._search_backend = FtsSearchBackend(db)

    def replace_snapshot(
        self,
        snapshot: RemoteSnapshot,
        *,
        dataset_hash: str,
    ) -> None:
        """Replace the entire cache with a fresh remote snapshot."""
        self._snapshot_importer.replace_snapshot(snapshot)
        self._dataset_state_repo.set_hash(dataset_hash)

    def get_dataset_hash(self) -> str:
        """Return the locally cached remote dataset hash."""
        return self._dataset_state_repo.get_hash()

    def invalidate_dataset_hash(self) -> None:
        """Mark the locally cached dataset hash as stale."""
        self._dataset_state_repo.set_hash("")

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
                "parent_pk": group.parent_pk,
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
                    "detail_hash": idea.detail_hash,
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
            parent_pk=group.parent_pk,
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
            detail_hash=idea.detail_hash,
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

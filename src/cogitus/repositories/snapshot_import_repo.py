"""Shared repository for importing full remote snapshots into a database."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cogitus.api.mappers import (
    to_group_response,
    to_idea_response,
    to_tag_response,
)
from cogitus.models.group import Group
from cogitus.models.idea import Idea
from cogitus.models.idea_cursor_state import IdeaCursorState
from cogitus.models.idea_scroll_state import IdeaScrollState
from cogitus.models.tag import Tag
from cogitus.repositories.idea_cursor_state_repo import (
    IdeaCursorStateRepository,
)
from cogitus.repositories.idea_scroll_state_repo import (
    IdeaScrollStateRepository,
)
from cogitus.search.backend import FtsSearchBackend

if TYPE_CHECKING:
    from sqliter import SqliterDB

    from cogitus.api.schemas.response.group import GroupResponse
    from cogitus.api.schemas.response.idea import IdeaResponse
    from cogitus.api.schemas.response.tag import TagResponse
    from cogitus.backends.types import RemoteSnapshot


@dataclass(frozen=True)
class SnapshotImportProgress:
    """Progress update for one stage of snapshot import."""

    stage: str
    completed: int
    total: int


SnapshotImportCallback = Callable[[SnapshotImportProgress], None]


@dataclass(frozen=True)
class _StoredSnapshot:
    """Local snapshot used to restore state after post-swap failures."""

    groups: list[GroupResponse]
    tags: list[TagResponse]
    ideas: list[IdeaResponse]


class SnapshotImportRepository:
    """Replace a target database with a full remote snapshot."""

    def __init__(self, db: SqliterDB) -> None:
        """Initialize the importer with the target database."""
        self._db = db
        self._cursor_repo = IdeaCursorStateRepository(db)
        self._scroll_repo = IdeaScrollStateRepository(db)
        self._search_backend = FtsSearchBackend(db)

    def replace_snapshot(
        self,
        snapshot: RemoteSnapshot,
        *,
        progress_callback: SnapshotImportCallback | None = None,
    ) -> None:
        """Replace the target database with one full remote snapshot."""
        previous_snapshot = self._current_snapshot()
        cursor_positions = self._cursor_repo.list_positions()
        scroll_positions = self._scroll_repo.list_positions()
        swap_completed = False

        try:
            self._replace_relational_snapshot(
                snapshot,
                progress_callback=progress_callback,
            )
            swap_completed = True
            self._search_backend.rebuild()
            self._restore_cursor_positions(
                cursor_positions,
                valid_idea_pks={idea.pk for idea in snapshot.ideas},
            )
            self._restore_scroll_positions(
                scroll_positions,
                valid_idea_hashes={
                    idea.pk: idea.detail_hash for idea in snapshot.ideas
                },
            )
        # Intentionally catch broad Exception here so any ordinary post-swap
        # failure triggers rollback instead of leaving committed data with a
        # stale or empty search index.
        except Exception:
            if not swap_completed:
                raise
            self._restore_previous_snapshot(
                previous_snapshot,
                cursor_positions=cursor_positions,
                scroll_positions=scroll_positions,
            )
            raise

    def _replace_relational_snapshot(
        self,
        snapshot: RemoteSnapshot | _StoredSnapshot,
        *,
        progress_callback: SnapshotImportCallback | None,
    ) -> None:
        """Replace only the relational tables for one snapshot."""
        with self._db.connect():
            self._db.select(IdeaScrollState).delete()
            self._db.select(IdeaCursorState).delete()
            self._db.select(Idea).delete()
            self._db.select(Tag).delete()
            self._db.select(Group).delete()

            groups_by_pk = self._insert_groups(
                snapshot.groups,
                progress_callback=progress_callback,
            )
            tags_by_pk = self._insert_tags(
                snapshot.tags,
                progress_callback=progress_callback,
            )
            self._insert_ideas(
                snapshot.ideas,
                groups_by_pk=groups_by_pk,
                tags_by_pk=tags_by_pk,
                progress_callback=progress_callback,
            )

    def _restore_previous_snapshot(
        self,
        snapshot: _StoredSnapshot,
        *,
        cursor_positions: dict[int, int],
        scroll_positions: dict[int, tuple[str, int]],
    ) -> None:
        """Restore the previous snapshot after a post-swap failure."""
        self._replace_relational_snapshot(snapshot, progress_callback=None)
        self._search_backend.rebuild()
        self._restore_cursor_positions(
            cursor_positions,
            valid_idea_pks={idea.pk for idea in snapshot.ideas},
        )
        self._restore_scroll_positions(
            scroll_positions,
            valid_idea_hashes={
                idea.pk: idea.detail_hash for idea in snapshot.ideas
            },
        )

    def _current_snapshot(self) -> _StoredSnapshot:
        """Return the current local dataset as a snapshot."""
        return _StoredSnapshot(
            groups=[
                to_group_response(group)
                for group in self._db.select(Group).order("pk").fetch_all()
            ],
            tags=[
                to_tag_response(tag)
                for tag in self._db.select(Tag).order("pk").fetch_all()
            ],
            ideas=[
                to_idea_response(idea)
                for idea in self._db.select(Idea).order("pk").fetch_all()
            ],
        )

    def _insert_groups(
        self,
        groups: list[GroupResponse],
        *,
        progress_callback: SnapshotImportCallback | None,
    ) -> dict[int, Group]:
        """Insert snapshot groups and return them keyed by primary key."""
        if progress_callback is None:
            return self._bulk_insert_groups(groups)
        self._report_progress("Groups", 0, len(groups), progress_callback)
        inserted: dict[int, Group] = {}
        for index, group in enumerate(groups, start=1):
            cached_group = self._db.insert(
                self._group_model(group),
                timestamp_override=True,
            )
            inserted[cached_group.pk] = cached_group
            self._report_progress(
                "Groups",
                index,
                len(groups),
                progress_callback,
            )
        self._validate_snapshot_group_parents(groups, inserted)
        return inserted

    def _insert_tags(
        self,
        tags: list[TagResponse],
        *,
        progress_callback: SnapshotImportCallback | None,
    ) -> dict[int, Tag]:
        """Insert snapshot tags and return them keyed by primary key."""
        if progress_callback is None:
            return self._bulk_insert_tags(tags)
        self._report_progress("Tags", 0, len(tags), progress_callback)
        inserted: dict[int, Tag] = {}
        for index, tag in enumerate(tags, start=1):
            cached_tag = self._db.insert(
                self._tag_model(tag),
                timestamp_override=True,
            )
            inserted[cached_tag.pk] = cached_tag
            self._report_progress(
                "Tags",
                index,
                len(tags),
                progress_callback,
            )
        return inserted

    def _insert_ideas(
        self,
        ideas: list[IdeaResponse],
        *,
        groups_by_pk: dict[int, Group],
        tags_by_pk: dict[int, Tag],
        progress_callback: SnapshotImportCallback | None,
    ) -> None:
        """Insert snapshot ideas and restore their tag links."""
        if progress_callback is None:
            resolved_ideas = self._resolve_snapshot_idea_relations(
                ideas,
                groups_by_pk=groups_by_pk,
                tags_by_pk=tags_by_pk,
            )
            cached_ideas_by_pk = self._bulk_insert_ideas(
                resolved_ideas,
            )
            self._sync_snapshot_idea_tags(
                resolved_ideas,
                cached_ideas_by_pk=cached_ideas_by_pk,
            )
            return
        self._report_progress("Ideas", 0, len(ideas), progress_callback)
        for index, idea in enumerate(ideas, start=1):
            resolved = self._resolve_snapshot_idea(
                idea,
                groups_by_pk=groups_by_pk,
                tags_by_pk=tags_by_pk,
            )
            cached_idea = self._db.insert(
                self._idea_model(idea, resolved.group),
                timestamp_override=True,
            )
            cached_idea.tags.set(*resolved.tags)
            self._report_progress(
                "Ideas",
                index,
                len(ideas),
                progress_callback,
            )

    @dataclass(frozen=True)
    class _ResolvedSnapshotIdea:
        """Snapshot idea with validated local group and tag references."""

        idea: IdeaResponse
        group: Group
        tags: list[Tag]

    def _resolve_snapshot_idea_relations(
        self,
        ideas: list[IdeaResponse],
        *,
        groups_by_pk: dict[int, Group],
        tags_by_pk: dict[int, Tag],
    ) -> list[_ResolvedSnapshotIdea]:
        """Resolve and validate snapshot idea relations."""
        return [
            self._resolve_snapshot_idea(
                idea,
                groups_by_pk=groups_by_pk,
                tags_by_pk=tags_by_pk,
            )
            for idea in ideas
        ]

    def _resolve_snapshot_idea(
        self,
        idea: IdeaResponse,
        *,
        groups_by_pk: dict[int, Group],
        tags_by_pk: dict[int, Tag],
    ) -> _ResolvedSnapshotIdea:
        """Resolve one snapshot idea's group and tag relations."""
        try:
            group = groups_by_pk[idea.group.pk]
        except KeyError:
            msg = (
                "Snapshot is inconsistent: "
                f"idea {idea.pk} references missing group "
                f"{idea.group.pk}"
            )
            raise RuntimeError(msg) from None
        try:
            tags = [tags_by_pk[tag.pk] for tag in idea.tags]
        except KeyError as exc:
            missing_tag_pk = exc.args[0]
            msg = (
                "Snapshot is inconsistent: "
                f"idea {idea.pk} references missing tag "
                f"{missing_tag_pk}"
            )
            raise RuntimeError(msg) from None
        return self._ResolvedSnapshotIdea(idea=idea, group=group, tags=tags)

    def _bulk_insert_groups(
        self,
        groups: list[GroupResponse],
    ) -> dict[int, Group]:
        """Insert snapshot groups in one batch."""
        if not groups:
            return {}
        inserted = self._db.bulk_insert(
            [self._group_model(group) for group in groups],
            timestamp_override=True,
        )
        inserted_by_pk = {group.pk: group for group in inserted}
        self._validate_snapshot_group_parents(groups, inserted_by_pk)
        return inserted_by_pk

    def _bulk_insert_tags(
        self,
        tags: list[TagResponse],
    ) -> dict[int, Tag]:
        """Insert snapshot tags in one batch."""
        if not tags:
            return {}
        inserted = self._db.bulk_insert(
            [self._tag_model(tag) for tag in tags],
            timestamp_override=True,
        )
        return {tag.pk: tag for tag in inserted}

    def _bulk_insert_ideas(
        self,
        ideas: list[_ResolvedSnapshotIdea],
    ) -> dict[int, Idea]:
        """Insert snapshot ideas in one batch."""
        if not ideas:
            return {}
        inserted = self._db.bulk_insert(
            [
                self._idea_model(
                    resolved.idea,
                    resolved.group,
                )
                for resolved in ideas
            ],
            timestamp_override=True,
        )
        return {idea.pk: idea for idea in inserted}

    def _sync_snapshot_idea_tags(
        self,
        ideas: list[_ResolvedSnapshotIdea],
        *,
        cached_ideas_by_pk: dict[int, Idea],
    ) -> None:
        """Recreate snapshot idea-tag links through the ORM M2M API."""
        for resolved in ideas:
            cached_idea = cached_ideas_by_pk.get(resolved.idea.pk)
            if cached_idea is None:
                msg = f"Idea {resolved.idea.pk} not found after snapshot insert"
                raise RuntimeError(msg)
            cached_idea.tags.set(*resolved.tags)

    def _restore_cursor_positions(
        self,
        cursor_positions: dict[int, int],
        *,
        valid_idea_pks: set[int],
    ) -> None:
        """Restore cursor positions for ideas that still exist."""
        for idea_pk, position in cursor_positions.items():
            if idea_pk in valid_idea_pks:
                self._cursor_repo.set_position(idea_pk, position)

    def _restore_scroll_positions(
        self,
        scroll_positions: dict[int, tuple[str, int]],
        *,
        valid_idea_hashes: dict[int, str],
    ) -> None:
        """Restore scroll positions for unchanged ideas that still exist."""
        for idea_pk, (detail_hash, scroll_y) in scroll_positions.items():
            if valid_idea_hashes.get(idea_pk) == detail_hash:
                self._scroll_repo.set_position(
                    idea_pk,
                    detail_hash,
                    scroll_y,
                )

    @staticmethod
    def _report_progress(
        stage: str,
        completed: int,
        total: int,
        progress_callback: SnapshotImportCallback | None,
    ) -> None:
        """Emit one progress update when a callback is available."""
        if progress_callback is None:
            return
        progress_callback(
            SnapshotImportProgress(
                stage=stage,
                completed=completed,
                total=total,
            )
        )

    @staticmethod
    def _group_model(group: GroupResponse) -> Group:
        """Build a group model from an API response."""
        return Group(
            pk=group.pk,
            created_at=group.created_at,
            updated_at=group.updated_at,
            name=group.name,
            parent_pk=group.parent_pk,
        )

    @staticmethod
    def _validate_snapshot_group_parents(
        groups: list[GroupResponse],
        inserted_by_pk: dict[int, Group],
    ) -> None:
        """Fail clearly when snapshot group parent links are inconsistent."""
        parent_by_pk = {group.pk: group.parent_pk for group in groups}
        for group in groups:
            parent_pk = group.parent_pk
            if parent_pk is None:
                continue
            if parent_pk == group.pk:
                msg = (
                    "Snapshot is inconsistent: "
                    f"group {group.pk} has self-referencing parent "
                    f"{parent_pk}"
                )
                raise RuntimeError(msg)
            if parent_pk not in inserted_by_pk:
                msg = (
                    "Snapshot is inconsistent: "
                    f"group {group.pk} references missing parent "
                    f"{parent_pk}"
                )
                raise RuntimeError(msg)
            seen: set[int] = {group.pk}
            current_pk: int | None = parent_pk
            while current_pk is not None:
                if current_pk in seen:
                    msg = (
                        "Snapshot is inconsistent: "
                        f"group {group.pk} parent chain contains a cycle"
                    )
                    raise RuntimeError(msg)
                seen.add(current_pk)
                current_pk = parent_by_pk.get(current_pk)

    @staticmethod
    def _tag_model(tag: TagResponse) -> Tag:
        """Build a tag model from an API response."""
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
        """Build an idea model from an API response."""
        return Idea(
            pk=idea.pk,
            created_at=idea.created_at,
            updated_at=idea.updated_at,
            title=idea.title,
            body=idea.body,
            detail_hash=idea.detail_hash,
            group=group,
        )

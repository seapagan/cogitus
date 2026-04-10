"""Shared repository for importing full remote snapshots into a database."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cogitus.models.group import Group
from cogitus.models.idea import Idea
from cogitus.models.idea_cursor_state import IdeaCursorState
from cogitus.models.tag import Tag
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


@dataclass(frozen=True)
class SnapshotImportProgress:
    """Progress update for one stage of snapshot import."""

    stage: str
    completed: int
    total: int


SnapshotImportCallback = Callable[[SnapshotImportProgress], None]


class SnapshotImportRepository:
    """Replace a target database with a full remote snapshot."""

    def __init__(self, db: SqliterDB) -> None:
        """Initialize the importer with the target database."""
        self._db = db
        self._cursor_repo = IdeaCursorStateRepository(db)
        self._search_backend = FtsSearchBackend(db)

    def replace_snapshot(
        self,
        snapshot: RemoteSnapshot,
        *,
        progress_callback: SnapshotImportCallback | None = None,
    ) -> None:
        """Replace the target database with one full remote snapshot."""
        cursor_positions = self._cursor_repo.list_positions()

        with self._db.connect():
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

        self._search_backend.rebuild()
        self._restore_cursor_positions(
            cursor_positions,
            valid_idea_pks={idea.pk for idea in snapshot.ideas},
        )

    def _insert_groups(
        self,
        groups: list[GroupResponse],
        *,
        progress_callback: SnapshotImportCallback | None,
    ) -> dict[int, Group]:
        """Insert snapshot groups and return them keyed by primary key."""
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
        return inserted

    def _insert_tags(
        self,
        tags: list[TagResponse],
        *,
        progress_callback: SnapshotImportCallback | None,
    ) -> dict[int, Tag]:
        """Insert snapshot tags and return them keyed by primary key."""
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
        self._report_progress("Ideas", 0, len(ideas), progress_callback)
        for index, idea in enumerate(ideas, start=1):
            cached_idea = self._db.insert(
                self._idea_model(idea, groups_by_pk[idea.group.pk]),
                timestamp_override=True,
            )
            cached_idea.tags.set(*(tags_by_pk[tag.pk] for tag in idea.tags))
            self._report_progress(
                "Ideas",
                index,
                len(ideas),
                progress_callback,
            )

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
        )

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
            group=group,
        )

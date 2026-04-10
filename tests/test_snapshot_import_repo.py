"""Tests for shared snapshot-import behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.api.schemas.response.group import GroupResponse
from cogitus.api.schemas.response.idea import IdeaResponse
from cogitus.api.schemas.response.tag import TagResponse
from cogitus.backends.types import RemoteSnapshot
from cogitus.repositories.snapshot_import_repo import SnapshotImportRepository
from cogitus.services.idea_service import IdeaService

if TYPE_CHECKING:
    from sqliter import SqliterDB


def _group(
    *,
    pk: int,
    name: str,
    created_at: int,
    updated_at: int,
) -> GroupResponse:
    """Build a group response for snapshot-import tests."""
    return GroupResponse(
        pk=pk,
        created_at=created_at,
        updated_at=updated_at,
        name=name,
    )


def _tag(
    *,
    pk: int,
    name: str,
    created_at: int,
    updated_at: int,
) -> TagResponse:
    """Build a tag response for snapshot-import tests."""
    return TagResponse(
        pk=pk,
        created_at=created_at,
        updated_at=updated_at,
        name=name,
    )


def _idea(
    *,
    pk: int,
    title: str,
    body: str,
    group: GroupResponse,
    tags: list[TagResponse],
    timestamps: tuple[int, int],
) -> IdeaResponse:
    """Build an idea response for snapshot-import tests."""
    return IdeaResponse(
        pk=pk,
        created_at=timestamps[0],
        updated_at=timestamps[1],
        title=title,
        body=body,
        group=group,
        tags=tags,
    )


def test_snapshot_import_replaces_db_and_preserves_cursor_state(
    db: SqliterDB,
) -> None:
    """Importing a snapshot should preserve cursor state for surviving ideas."""
    service = IdeaService(db)
    importer = SnapshotImportRepository(db)
    placeholder = service.create_idea("Placeholder")
    service.set_idea_cursor_position(placeholder.pk, 9)

    default_group = _group(pk=1, name="default", created_at=1, updated_at=1)
    python_tag = _tag(pk=1, name="python", created_at=2, updated_at=2)
    cli_tag = _tag(pk=2, name="cli", created_at=3, updated_at=3)
    snapshot = RemoteSnapshot(
        groups=[default_group],
        tags=[python_tag, cli_tag],
        ideas=[
            _idea(
                pk=1,
                title="Imported idea",
                body="Local clone body",
                group=default_group,
                tags=[python_tag, cli_tag],
                timestamps=(4, 5),
            )
        ],
    )

    importer.replace_snapshot(snapshot)

    imported = service.get_idea_with_relations(1)
    assert imported is not None
    assert imported.title == "Imported idea"
    assert sorted(tag.name for tag in imported.tags.fetch_all()) == [
        "cli",
        "python",
    ]
    assert service.get_idea_cursor_position(1) == 9
    assert service.search_results("tag:cli")[0].idea.pk == 1

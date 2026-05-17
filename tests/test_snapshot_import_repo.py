"""Tests for shared snapshot-import behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from cogitus.api.schemas.response.group import GroupResponse
from cogitus.api.schemas.response.idea import IdeaResponse
from cogitus.api.schemas.response.tag import TagResponse
from cogitus.backends.types import RemoteSnapshot
from cogitus.hashing import idea_detail_hash
from cogitus.repositories.snapshot_import_repo import SnapshotImportRepository
from cogitus.services.idea_service import IdeaService

if TYPE_CHECKING:
    from pytest_mock import MockerFixture
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
        detail_hash=idea_detail_hash(
            title=title,
            body=body,
            tag_names=[tag.name for tag in tags],
            created_at=timestamps[0],
            updated_at=timestamps[1],
        ),
        group=group,
        tags=tags,
    )


def _assert_first_search_hit_pk(
    service: IdeaService,
    query: str,
) -> int:
    """Assert a search query returns at least one result and return its PK."""
    results = service.search_results(query)
    assert results, f"Expected at least one search result for query: {query!r}"
    return results[0].idea.pk


def test_snapshot_import_replaces_db_and_preserves_cursor_state(
    db: SqliterDB,
) -> None:
    """Importing a snapshot should preserve cursor state for surviving ideas."""
    service = IdeaService(db)
    importer = SnapshotImportRepository(db)
    placeholder = service.create_idea("Placeholder")
    extra_local = service.create_idea("Should be removed")
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
    service.set_idea_scroll_position(
        placeholder.pk,
        snapshot.ideas[0].detail_hash,
        13,
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
    assert service.get_idea_scroll_position(1, imported.detail_hash) == 13
    assert _assert_first_search_hit_pk(service, "tag:cli") == 1
    assert service.get_idea_with_relations(extra_local.pk) is None


def test_snapshot_import_restores_previous_state_if_rebuild_fails(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """A rebuild failure should restore the pre-import data and search index."""
    service = IdeaService(db)
    importer = SnapshotImportRepository(db)
    local = service.create_idea("Local idea", body="Keep this", tags=["local"])
    service.set_idea_cursor_position(local.pk, 7)

    default_group = _group(pk=1, name="default", created_at=1, updated_at=1)
    remote_tag = _tag(pk=1, name="remote", created_at=2, updated_at=2)
    snapshot = RemoteSnapshot(
        groups=[default_group],
        tags=[remote_tag],
        ideas=[
            _idea(
                pk=1,
                title="Imported idea",
                body="Replaced body",
                group=default_group,
                tags=[remote_tag],
                timestamps=(4, 5),
            )
        ],
    )

    original_rebuild = importer._search_backend.rebuild
    calls = 0

    def fail_first_rebuild() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            msg = "fts rebuild failed"
            raise RuntimeError(msg)
        original_rebuild()

    mocker.patch.object(
        importer._search_backend,
        "rebuild",
        side_effect=fail_first_rebuild,
    )

    with pytest.raises(RuntimeError, match="fts rebuild failed"):
        importer.replace_snapshot(snapshot)

    restored = service.get_idea_with_relations(local.pk)
    assert restored is not None
    assert restored.title == "Local idea"
    assert [tag.name for tag in restored.tags.fetch_all()] == ["local"]
    assert service.get_idea_cursor_position(local.pk) == 7
    assert _assert_first_search_hit_pk(service, "tag:local") == local.pk
    same_pk = service.get_idea_with_relations(1)
    assert same_pk is not None
    assert same_pk.title == "Local idea"


def test_snapshot_import_restores_previous_state_if_cursor_restore_fails(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """A cursor-restore failure should also restore the pre-import state."""
    service = IdeaService(db)
    importer = SnapshotImportRepository(db)
    local = service.create_idea("Local idea", body="Keep this", tags=["local"])
    service.set_idea_cursor_position(local.pk, 11)

    default_group = _group(pk=1, name="default", created_at=1, updated_at=1)
    remote_tag = _tag(pk=1, name="remote", created_at=2, updated_at=2)
    snapshot = RemoteSnapshot(
        groups=[default_group],
        tags=[remote_tag],
        ideas=[
            _idea(
                pk=1,
                title="Imported idea",
                body="Replaced body",
                group=default_group,
                tags=[remote_tag],
                timestamps=(4, 5),
            )
        ],
    )

    original_restore = importer._restore_cursor_positions
    calls = 0

    def fail_first_restore(
        cursor_positions: dict[int, int],
        *,
        valid_idea_pks: set[int],
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            msg = "cursor restore failed"
            raise RuntimeError(msg)
        original_restore(
            cursor_positions,
            valid_idea_pks=valid_idea_pks,
        )

    mocker.patch.object(
        importer,
        "_restore_cursor_positions",
        side_effect=fail_first_restore,
    )

    with pytest.raises(RuntimeError, match="cursor restore failed"):
        importer.replace_snapshot(snapshot)

    restored = service.get_idea_with_relations(local.pk)
    assert restored is not None
    assert restored.title == "Local idea"
    assert [tag.name for tag in restored.tags.fetch_all()] == ["local"]
    assert service.get_idea_cursor_position(local.pk) == 11
    assert _assert_first_search_hit_pk(service, "tag:local") == local.pk
    same_pk = service.get_idea_with_relations(1)
    assert same_pk is not None
    assert same_pk.title == "Local idea"


def test_snapshot_import_uses_bulk_insert_without_progress_callback(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Full snapshot replacement should keep the efficient bulk insert path."""
    importer = SnapshotImportRepository(db)
    bulk_insert = mocker.patch.object(db, "bulk_insert", wraps=db.bulk_insert)
    get = mocker.patch.object(db, "get", wraps=db.get)
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

    assert bulk_insert.call_count == 3
    get.assert_not_called()


def test_snapshot_import_with_progress_callback_uses_rowwise_progress_path(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Progress-aware imports should avoid bulk insert and emit updates."""
    service = IdeaService(db)
    importer = SnapshotImportRepository(db)
    bulk_insert = mocker.patch.object(db, "bulk_insert", wraps=db.bulk_insert)
    updates: list[tuple[str, int, int]] = []
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

    importer.replace_snapshot(
        snapshot,
        progress_callback=lambda progress: updates.append(
            (progress.stage, progress.completed, progress.total)
        ),
    )

    imported = service.get_idea_with_relations(1)
    assert imported is not None
    assert imported.title == "Imported idea"
    assert imported.group.name == "default"
    assert sorted(tag.name for tag in imported.tags.fetch_all()) == [
        "cli",
        "python",
    ]
    assert _assert_first_search_hit_pk(service, "tag:cli") == 1
    assert bulk_insert.call_count == 0
    assert updates == [
        ("Groups", 0, 1),
        ("Groups", 1, 1),
        ("Tags", 0, 2),
        ("Tags", 1, 2),
        ("Tags", 2, 2),
        ("Ideas", 0, 1),
        ("Ideas", 1, 1),
    ]


def test_snapshot_import_sync_snapshot_idea_tags_requires_inserted_idea(
    db: SqliterDB,
) -> None:
    """Snapshot tag relinking should fail clearly if an idea row is missing."""
    importer = SnapshotImportRepository(db)
    default_group = _group(pk=2, name="default-2", created_at=1, updated_at=1)
    python_tag = _tag(pk=2, name="python", created_at=2, updated_at=2)
    groups_by_pk = importer._bulk_insert_groups([default_group])
    tags_by_pk = importer._bulk_insert_tags([python_tag])
    ideas = [
        _idea(
            pk=1,
            title="Imported idea",
            body="Local clone body",
            group=default_group,
            tags=[python_tag],
            timestamps=(4, 5),
        )
    ]
    resolved_ideas = importer._resolve_snapshot_idea_relations(
        ideas,
        groups_by_pk=groups_by_pk,
        tags_by_pk=tags_by_pk,
    )

    with pytest.raises(
        RuntimeError,
        match="Idea 1 not found after snapshot insert",
    ):
        importer._sync_snapshot_idea_tags(
            resolved_ideas,
            cached_ideas_by_pk={},
        )


def test_snapshot_import_progress_path_reports_missing_group(
    db: SqliterDB,
) -> None:
    """Progress-aware import should fail clearly on missing snapshot groups."""
    importer = SnapshotImportRepository(db)
    python_tag = _tag(pk=1, name="python", created_at=2, updated_at=2)
    missing_group = _group(pk=99, name="missing", created_at=1, updated_at=1)
    snapshot = RemoteSnapshot(
        groups=[],
        tags=[python_tag],
        ideas=[
            _idea(
                pk=1,
                title="Imported idea",
                body="Local clone body",
                group=missing_group,
                tags=[python_tag],
                timestamps=(4, 5),
            )
        ],
    )

    with pytest.raises(
        RuntimeError,
        match="idea 1 references missing group 99",
    ):
        importer.replace_snapshot(
            snapshot,
            progress_callback=lambda _progress: None,
        )


def test_snapshot_import_bulk_path_reports_missing_group(
    db: SqliterDB,
) -> None:
    """Bulk import should fail clearly on missing snapshot groups."""
    importer = SnapshotImportRepository(db)
    python_tag = _tag(pk=1, name="python", created_at=2, updated_at=2)
    missing_group = _group(pk=99, name="missing", created_at=1, updated_at=1)
    snapshot = RemoteSnapshot(
        groups=[],
        tags=[python_tag],
        ideas=[
            _idea(
                pk=1,
                title="Imported idea",
                body="Local clone body",
                group=missing_group,
                tags=[python_tag],
                timestamps=(4, 5),
            )
        ],
    )

    with pytest.raises(
        RuntimeError,
        match="idea 1 references missing group 99",
    ):
        importer.replace_snapshot(snapshot)


def test_snapshot_import_progress_path_reports_missing_tag(
    db: SqliterDB,
) -> None:
    """Progress-aware import should fail clearly on missing snapshot tags."""
    importer = SnapshotImportRepository(db)
    default_group = _group(pk=1, name="default", created_at=1, updated_at=1)
    missing_tag = _tag(pk=99, name="missing", created_at=2, updated_at=2)
    snapshot = RemoteSnapshot(
        groups=[default_group],
        tags=[],
        ideas=[
            _idea(
                pk=1,
                title="Imported idea",
                body="Local clone body",
                group=default_group,
                tags=[missing_tag],
                timestamps=(4, 5),
            )
        ],
    )

    with pytest.raises(
        RuntimeError,
        match="idea 1 references missing tag 99",
    ):
        importer.replace_snapshot(
            snapshot,
            progress_callback=lambda _progress: None,
        )


def test_snapshot_import_bulk_path_reports_missing_tag(
    db: SqliterDB,
) -> None:
    """Bulk import should fail clearly on missing snapshot tags."""
    importer = SnapshotImportRepository(db)
    default_group = _group(pk=1, name="default", created_at=1, updated_at=1)
    missing_tag = _tag(pk=99, name="missing", created_at=2, updated_at=2)
    snapshot = RemoteSnapshot(
        groups=[default_group],
        tags=[],
        ideas=[
            _idea(
                pk=1,
                title="Imported idea",
                body="Local clone body",
                group=default_group,
                tags=[missing_tag],
                timestamps=(4, 5),
            )
        ],
    )

    with pytest.raises(
        RuntimeError,
        match="idea 1 references missing tag 99",
    ):
        importer.replace_snapshot(snapshot)


def test_snapshot_import_bulk_helpers_handle_empty_inputs(
    db: SqliterDB,
) -> None:
    """Bulk helper paths should accept empty snapshot sections."""
    importer = SnapshotImportRepository(db)

    assert importer._bulk_insert_groups([]) == {}
    assert importer._bulk_insert_tags([]) == {}
    assert importer._bulk_insert_ideas([]) == {}


def test_snapshot_import_reports_progress_when_callback_is_present() -> None:
    """Progress helper should emit a structured update when requested."""
    updates: list[Any] = []

    SnapshotImportRepository._report_progress(
        "Ideas",
        2,
        3,
        updates.append,
    )

    assert len(updates) == 1
    progress = updates[0]
    assert progress.stage == "Ideas"
    assert progress.completed == 2
    assert progress.total == 3


def test_snapshot_import_report_progress_ignores_missing_callback() -> None:
    """Progress helper should no-op when no callback is provided."""
    SnapshotImportRepository._report_progress("Ideas", 1, 1, None)

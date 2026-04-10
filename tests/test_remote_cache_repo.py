"""Tests for ORM-backed remote cache persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cogitus.api.schemas.response.group import GroupResponse
from cogitus.api.schemas.response.idea import IdeaResponse
from cogitus.api.schemas.response.tag import TagResponse
from cogitus.backends.types import RemoteSnapshot
from cogitus.models.group import Group
from cogitus.models.tag import Tag
from cogitus.repositories.remote_cache_repo import RemoteCacheRepository
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
    """Build a group API response for cache-repository tests."""
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
    """Build a tag API response for cache-repository tests."""
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
    """Build an idea API response for cache-repository tests."""
    return IdeaResponse(
        pk=pk,
        created_at=timestamps[0],
        updated_at=timestamps[1],
        title=title,
        body=body,
        group=group,
        tags=tags,
    )


def _upsert_initial_idea(
    repo: RemoteCacheRepository,
    *,
    with_tags: bool,
) -> None:
    """Insert the initial remote idea used in update-path tests."""
    default_group = _group(pk=1, name="default", created_at=1, updated_at=1)
    initial_tags = (
        [_tag(pk=1, name="python", created_at=2, updated_at=2)]
        if with_tags
        else []
    )

    repo.upsert_idea(
        _idea(
            pk=1,
            title="Remote idea",
            body="Initial body",
            group=default_group,
            tags=initial_tags,
            timestamps=(3, 3),
        )
    )


def _upsert_updated_idea(
    repo: RemoteCacheRepository,
    *,
    with_tags: bool,
) -> None:
    """Insert the refreshed remote group/tag state and updated idea."""
    updated_tags = (
        [_tag(pk=2, name="httpx", created_at=5, updated_at=11)]
        if with_tags
        else []
    )

    repo.upsert_group(
        _group(
            pk=2,
            name="platform",
            created_at=4,
            updated_at=9,
        )
    )
    if with_tags:
        repo.upsert_tag(
            _tag(
                pk=2,
                name="httpx",
                created_at=5,
                updated_at=11,
            )
        )
    repo.upsert_idea(
        _idea(
            pk=1,
            title="Updated remote idea",
            body="Changed body",
            group=_group(
                pk=2,
                name="platform",
                created_at=4,
                updated_at=9,
            ),
            tags=updated_tags,
            timestamps=(3, 12),
        )
    )


def test_replace_snapshot_preserves_cursor_and_tags(
    db: SqliterDB,
) -> None:
    """Snapshot replacement should preserve cursor state for surviving ideas."""
    service = IdeaService(db)
    repo = RemoteCacheRepository(db, default_group_name="default")
    local = service.create_idea("Local placeholder")
    service.set_idea_cursor_position(local.pk, 12)

    default_group = _group(pk=1, name="default", created_at=1, updated_at=1)
    python_tag = _tag(pk=1, name="python", created_at=2, updated_at=2)
    api_tag = _tag(pk=2, name="api", created_at=3, updated_at=3)
    snapshot = RemoteSnapshot(
        groups=[default_group],
        tags=[python_tag, api_tag],
        ideas=[
            _idea(
                pk=1,
                title="Seed idea",
                body="Seed body",
                group=default_group,
                tags=[python_tag, api_tag],
                timestamps=(4, 5),
            )
        ],
    )

    repo.replace_snapshot(snapshot)

    synced = service.get_idea_with_relations(1)
    assert synced is not None
    assert synced.title == "Seed idea"
    assert synced.updated_at == 5
    assert synced.group.name == "default"
    assert sorted(tag.name for tag in synced.tags.fetch_all()) == [
        "api",
        "python",
    ]
    assert service.get_idea_cursor_position(1) == 12
    assert service.search_results("tag:api")[0].idea.pk == 1


def test_replace_snapshot_handles_empty_tag_and_idea_lists(
    db: SqliterDB,
) -> None:
    """Snapshot replacement should handle empty tag and idea payloads."""
    service = IdeaService(db)
    repo = RemoteCacheRepository(db, default_group_name="default")

    repo.replace_snapshot(
        RemoteSnapshot(
            groups=[_group(pk=1, name="default", created_at=1, updated_at=1)],
            tags=[],
            ideas=[],
        )
    )

    assert service.list_groups()[0].name == "default"
    assert service.list_ideas() == []
    assert service.list_tags() == []


def test_upsert_group_and_tag_update_existing_rows(
    db: SqliterDB,
) -> None:
    """Group and tag upserts should preserve remote timestamps."""
    repo = RemoteCacheRepository(db, default_group_name="default")
    repo.upsert_group(
        _group(
            pk=2,
            name="backend",
            created_at=4,
            updated_at=4,
        )
    )
    repo.upsert_group(
        _group(
            pk=2,
            name="platform",
            created_at=4,
            updated_at=9,
        )
    )
    repo.upsert_tag(
        _tag(
            pk=2,
            name="http",
            created_at=5,
            updated_at=5,
        )
    )
    repo.upsert_tag(
        _tag(
            pk=2,
            name="httpx",
            created_at=5,
            updated_at=11,
        )
    )

    cached_group = repo._db.select(Group).filter(pk=2).fetch_one()
    cached_tag = repo._db.select(Tag).filter(pk=2).fetch_one()

    assert cached_group is not None
    assert cached_group.name == "platform"
    assert cached_group.created_at == 4
    assert cached_group.updated_at == 9
    assert cached_tag is not None
    assert cached_tag.name == "httpx"
    assert cached_tag.created_at == 5
    assert cached_tag.updated_at == 11


def test_upsert_idea_updates_existing_rows_and_links(
    db: SqliterDB,
) -> None:
    """Idea upserts should preserve remote timestamps and replace links."""
    service = IdeaService(db)
    repo = RemoteCacheRepository(db, default_group_name="default")
    _upsert_initial_idea(repo, with_tags=True)
    _upsert_updated_idea(repo, with_tags=True)

    cached = service.get_idea_with_relations(1)
    assert cached is not None
    assert cached.title == "Updated remote idea"
    assert cached.body == "Changed body"
    assert cached.updated_at == 12
    assert cached.group.name == "platform"
    assert [tag.name for tag in cached.tags.fetch_all()] == ["httpx"]


def test_upsert_idea_rebuilds_search_index_with_updated_group(
    db: SqliterDB,
) -> None:
    """Rebuilding search after an idea upsert should reflect the new group."""
    service = IdeaService(db)
    repo = RemoteCacheRepository(db, default_group_name="default")
    _upsert_initial_idea(repo, with_tags=False)
    _upsert_updated_idea(repo, with_tags=False)
    repo.rebuild_search_index()

    assert service.search_results("group:platform")[0].idea.pk == 1


def test_delete_operations_update_cache_without_raw_sql(
    db: SqliterDB,
) -> None:
    """Delete operations should mirror remote cache changes correctly."""
    service = IdeaService(db)
    repo = RemoteCacheRepository(db, default_group_name="default")
    default_group = _group(pk=1, name="default", created_at=1, updated_at=1)
    backend_group = _group(pk=2, name="backend", created_at=2, updated_at=2)
    python_tag = _tag(pk=1, name="python", created_at=3, updated_at=3)

    repo.upsert_idea(
        _idea(
            pk=1,
            title="Move me",
            body="Body",
            group=backend_group,
            tags=[python_tag],
            timestamps=(4, 4),
        )
    )
    repo.upsert_idea(
        _idea(
            pk=2,
            title="Delete me",
            body="Body",
            group=default_group,
            tags=[python_tag],
            timestamps=(5, 5),
        )
    )
    service.set_idea_cursor_position(2, 8)

    repo.delete_idea(2)
    repo.delete_group(2, move_to_group_pk=None)

    moved = service.get_idea_with_relations(1)
    assert moved is not None
    assert moved.group.pk == 1
    assert moved.group.name == "default"
    assert service.get_idea(2) is None
    assert service.get_idea_cursor_position(2) is None
    assert service.search_results("group:default")[0].idea.pk == 1


def test_delete_group_guard_paths(
    db: SqliterDB,
) -> None:
    """Cache group-delete guards should raise clearly on invalid state."""
    repo = RemoteCacheRepository(db, default_group_name="default")

    repo.delete_group(999, move_to_group_pk=None)

    repo.upsert_group(_group(pk=2, name="backend", created_at=2, updated_at=2))

    db.delete(Group, 1)
    with pytest.raises(RuntimeError, match="Default group missing"):
        repo.delete_group(2, move_to_group_pk=None)

    repo.upsert_group(_group(pk=1, name="default", created_at=1, updated_at=1))
    with pytest.raises(
        RuntimeError,
        match="Cannot move cached ideas into the group being deleted",
    ):
        repo.delete_group(1, move_to_group_pk=None)


def test_internal_helper_guards_cover_empty_and_missing_cache_paths(
    db: SqliterDB,
) -> None:
    """Private guard helpers should fail clearly for missing cache rows."""
    repo = RemoteCacheRepository(db, default_group_name="default")

    with pytest.raises(RuntimeError, match="Group 999 not found"):
        repo._require_group(999)
    with pytest.raises(RuntimeError, match="Tag 999 not found"):
        repo._require_tag(999)
    with pytest.raises(RuntimeError, match="Idea 999 not found"):
        repo._require_idea(999)

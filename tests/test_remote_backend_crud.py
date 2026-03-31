"""Tests for remote backend CRUD and cache-guard behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cogitus.backends.api_client import RemoteAPIClient
from cogitus.backends.remote_backend import RemoteIdeaBackend
from tests.remote_api_support import (
    REMOTE_USERNAME,
    MockRemoteAPI,
    remote_secret,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture, MockType
    from sqliter import SqliterDB


def _build_cached_snapshot(mocker: MockerFixture) -> object:
    """Return a cached idea snapshot with stable related fields."""
    tags = [mocker.Mock(), mocker.Mock()]
    tags[0].name = "tag-one"
    tags[1].name = "tag-two"
    snapshot = mocker.Mock(
        body="Old body",
        group=mocker.Mock(pk=7),
        updated_at=11,
    )
    snapshot.tags.fetch_all.return_value = tags
    return snapshot


def _assert_update_request(
    update_idea: MockType,
) -> None:
    """Assert rename_idea forwarded one consistent cached snapshot."""
    update_call = update_idea.call_args
    assert update_call is not None
    assert update_call.args[0] == 5
    request = update_call.args[1]
    assert request.title == "Renamed title"
    assert request.body == "Old body"
    assert request.tags == ["tag-one", "tag-two"]
    assert request.group_pk == 7
    assert request.last_known_updated_at == 11


def test_remote_backend_sync_populates_cache_and_preserves_cursor(
    db: SqliterDB,
) -> None:
    """Full remote sync should replace cache rows but keep cursor state."""
    cache_service = RemoteIdeaBackend(
        db,
        default_group_name="default",
        api_client=RemoteAPIClient(
            base_url="http://remote.test",
            username=REMOTE_USERNAME,
            password=remote_secret(),
            transport=MockRemoteAPI().transport(),
        ),
    )
    local = cache_service._cache_service
    local.create_idea("Local placeholder")
    local.set_idea_cursor_position(1, 12)

    cache_service.sync_from_remote()

    synced = cache_service.get_idea(1)
    assert synced is not None
    assert synced.title == "Seed idea"
    assert cache_service.get_idea_cursor_position(1) == 12


def test_remote_backend_delegate_and_guard_paths(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Read delegates and missing-record guards should behave correctly."""
    api_client = mocker.Mock()
    backend = RemoteIdeaBackend(
        db,
        default_group_name="default",
        api_client=api_client,
    )
    seed = backend._cache_service.create_idea("Seed idea", tags=["python"])

    assert backend.update_idea(999, "Missing", "", tags=[], group_pk=1) is None
    assert backend.rename_idea(999, "Missing") is None
    assert backend.rename_group(999, "missing") is None
    assert backend.get_idea(seed.pk) is not None
    assert backend.get_group(seed.group.pk) is not None
    assert backend.list_tags_in_use()[0].name == "python"
    assert backend.list_tags_with_usage()[0][1] == 1
    backend.set_idea_cursor_position(seed.pk, 7)
    assert backend.get_idea_cursor_position(seed.pk) == 7
    assert backend.has_ideas_in_group(seed.group.pk) is True
    assert backend.list_groups()[0].name == "default"
    assert backend.list_ideas_grouped()[0][1][0].pk == seed.pk
    assert backend.search_results("Seed")[0].idea.pk == seed.pk

    rename_update = mocker.patch.object(
        backend, "_update_cached_idea", return_value=seed
    )
    assert backend.rename_idea(seed.pk, "Renamed") is seed
    rename_update.assert_called_once_with(
        seed.pk,
        title="Renamed",
        body="",
        tags=["python"],
        group_pk=seed.group.pk,
        last_known_updated_at=seed.updated_at,
    )

    mocker.patch.object(
        backend._cache_service,
        "get_idea_with_relations",
        return_value=None,
    )
    assert backend.rename_idea(seed.pk, "Renamed") is None

    backend.close()
    api_client.close.assert_called_once_with()


def test_remote_backend_rename_idea_uses_one_cached_snapshot(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Rename should keep payload fields and optimistic lock in step."""
    backend = RemoteIdeaBackend(
        db,
        default_group_name="default",
        api_client=mocker.Mock(),
    )
    updated = mocker.Mock(pk=5)
    renamed = mocker.Mock(name="renamed")

    mocker.patch.object(
        backend._cache_service,
        "get_idea_with_relations",
        return_value=_build_cached_snapshot(mocker),
    )
    mocker.patch.object(
        backend._cache_service,
        "get_idea",
        side_effect=AssertionError(
            "rename_idea should not re-read the cache timestamp"
        ),
    )
    update_idea = mocker.patch.object(
        backend._api_client,
        "update_idea",
        return_value=updated,
    )
    upsert_idea = mocker.patch.object(backend._cache_repo, "upsert_idea")
    require_cached = mocker.patch.object(
        backend,
        "_require_cached_idea",
        return_value=renamed,
    )

    assert backend.rename_idea(5, "Renamed title") is renamed
    _assert_update_request(update_idea)
    upsert_idea.assert_called_once_with(updated)
    require_cached.assert_called_once_with(updated.pk)


def test_remote_backend_internal_error_guards(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Internal cache guard helpers should raise clear runtime errors."""
    backend = RemoteIdeaBackend(
        db,
        default_group_name="default",
        api_client=mocker.Mock(),
    )

    mocker.patch.object(backend._cache_service, "get_group", return_value=None)
    with pytest.raises(RuntimeError, match="Group 1 not found in cache"):
        backend._require_cached_group(1)

    mocker.patch.object(backend._cache_service, "get_idea", return_value=None)
    with pytest.raises(RuntimeError, match="Idea 1 not found in cache"):
        backend._require_cached_idea(1)

    with pytest.raises(
        RuntimeError,
        match="Worker-thread sync requires a file-backed cache database",
    ):
        backend._build_worker_cache_db()

    backend._cache_db = mocker.Mock(is_memory=False, filename=None)
    with pytest.raises(
        RuntimeError,
        match="Remote cache database path is unavailable",
    ):
        backend._build_worker_cache_db()


def test_remote_backend_create_update_and_delete_idea_updates_cache(
    db: SqliterDB,
) -> None:
    """Idea writes should update the local cache without a full resync."""
    api = MockRemoteAPI()
    backend = RemoteIdeaBackend(
        db,
        default_group_name="default",
        api_client=RemoteAPIClient(
            base_url="http://remote.test",
            username=REMOTE_USERNAME,
            password=remote_secret(),
            transport=api.transport(),
        ),
    )
    backend.sync_from_remote()

    created = backend.create_idea(
        "Remote idea",
        body="Serve remotely",
        tags=["fastapi"],
        group_pk=1,
    )
    assert created.title == "Remote idea"
    assert backend.search_results("tag:fastapi")[0].idea.pk == created.pk

    updated = backend.update_idea(
        created.pk,
        "Updated remote idea",
        "Changed body",
        tags=["httpx"],
        group_pk=1,
    )
    assert updated is not None
    assert updated.title == "Updated remote idea"
    assert backend.search_results("tag:httpx")[0].idea.pk == created.pk

    backend.delete_idea(created.pk)
    assert backend.get_idea(created.pk) is None


def test_remote_backend_update_idea_raises_on_stale_cache(
    db: SqliterDB,
) -> None:
    """Remote updates should surface optimistic-lock conflicts."""
    api = MockRemoteAPI()
    backend = RemoteIdeaBackend(
        db,
        default_group_name="default",
        api_client=RemoteAPIClient(
            base_url="http://remote.test",
            username=REMOTE_USERNAME,
            password=remote_secret(),
            transport=api.transport(),
        ),
    )
    backend.sync_from_remote()
    api.mutate_idea(1, title="Changed elsewhere")

    with pytest.raises(ValueError, match="modified on the server"):
        backend.update_idea(
            1,
            "My edit",
            "Seed body",
            tags=["python"],
            group_pk=1,
        )


def test_remote_backend_group_operations_update_cache_and_search(
    db: SqliterDB,
) -> None:
    """Group writes should update cached group state and search data."""
    api = MockRemoteAPI()
    backend = RemoteIdeaBackend(
        db,
        default_group_name="default",
        api_client=RemoteAPIClient(
            base_url="http://remote.test",
            username=REMOTE_USERNAME,
            password=remote_secret(),
            transport=api.transport(),
        ),
    )
    backend.sync_from_remote()

    created_group = backend.create_group("backend")
    created_idea = backend.create_idea(
        "Grouped idea",
        body="Body",
        tags=["python"],
        group_pk=created_group.pk,
    )
    renamed_group = backend.rename_group(created_group.pk, "platform")

    assert renamed_group is not None
    assert (
        backend.search_results("group:platform")[0].idea.pk == created_idea.pk
    )

    backend.delete_group(created_group.pk)

    moved = backend.get_idea(created_idea.pk)
    assert moved is not None
    assert moved.group.pk == 1
    assert backend.get_group(created_group.pk) is None

"""Tests for the cache-backed remote backend."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest

from cogitus.backends.api_client import RemoteAPIClient
from cogitus.backends.remote_backend import RemoteIdeaBackend
from cogitus.db import get_db
from cogitus.repositories.remote_cache_repo import RemoteCacheRepository
from tests.remote_api_support import (
    REMOTE_USERNAME,
    MockRemoteAPI,
    remote_secret,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture
    from sqliter import SqliterDB


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
        backend, "update_idea", return_value=seed
    )
    assert backend.rename_idea(seed.pk, "Renamed") is seed
    rename_update.assert_called_once_with(
        seed.pk,
        title="Renamed",
        body="",
        tags=["python"],
        group_pk=seed.group.pk,
    )

    mocker.patch.object(backend._cache_service, "get_idea", return_value=seed)
    mocker.patch.object(
        backend._cache_service,
        "get_idea_with_relations",
        return_value=None,
    )
    assert backend.rename_idea(seed.pk, "Renamed") is None

    backend.close()
    api_client.close.assert_called_once_with()


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


def test_remote_backend_sync_from_worker_thread_uses_fresh_db_connection(
    tmp_path: Path,
) -> None:
    """Worker-thread sync should not reuse the main-thread SQLite connection."""
    cache_db = get_db(str(tmp_path / "remote-cache.db"))
    try:
        backend = RemoteIdeaBackend(
            cache_db,
            default_group_name="default",
            api_client=RemoteAPIClient(
                base_url="http://remote.test",
                username=REMOTE_USERNAME,
                password=remote_secret(),
                transport=MockRemoteAPI().transport(),
            ),
        )
        assert cache_db.is_connected is True

        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(backend.sync_from_remote).result()

        synced = backend.get_idea(1)
        assert synced is not None
        assert synced.title == "Seed idea"
    finally:
        cache_db.close()


def _build_remote_backend_for_file_cache(tmp_path: Path) -> RemoteIdeaBackend:
    """Create a file-backed remote backend for thread-sync tests."""
    cache_db = get_db(str(tmp_path / "remote-cache.db"))
    return RemoteIdeaBackend(
        cache_db,
        default_group_name="default",
        api_client=RemoteAPIClient(
            base_url="http://remote.test",
            username=REMOTE_USERNAME,
            password=remote_secret(),
            transport=MockRemoteAPI().transport(),
        ),
    )


def test_remote_backend_serializes_concurrent_snapshot_replacement(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Concurrent sync requests should not replace the cache in parallel."""
    backend = _build_remote_backend_for_file_cache(tmp_path)
    cache_db = backend._cache_db
    active = max_active = 0
    active_lock = threading.Lock()
    first_started, allow_exit = threading.Event(), threading.Event()

    def tracked_replace_snapshot(
        _repo: RemoteCacheRepository,
        _snapshot: object,
    ) -> None:
        nonlocal active, max_active
        with active_lock:
            active += 1
            max_active = max(max_active, active)
            first_started.set()
        try:
            allow_exit.wait(timeout=1)
        finally:
            with active_lock:
                active -= 1

    mocker.patch.object(
        RemoteCacheRepository,
        "replace_snapshot",
        autospec=True,
        side_effect=tracked_replace_snapshot,
    )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_one = executor.submit(backend.sync_from_remote)
            assert first_started.wait(timeout=1)
            future_two = executor.submit(backend.sync_from_remote)

            time.sleep(0.05)
            assert max_active == 1

            allow_exit.set()
            future_one.result()
            future_two.result()
    finally:
        cache_db.close()


def test_remote_backend_allows_follow_up_sync_after_serialized_run(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """A second sync should still run after the first serialized sync exits."""
    backend = _build_remote_backend_for_file_cache(tmp_path)
    cache_db = backend._cache_db
    replace_snapshot = mocker.patch.object(
        RemoteCacheRepository,
        "replace_snapshot",
        autospec=True,
    )

    try:
        backend.sync_from_remote()
        backend.sync_from_remote()
    finally:
        cache_db.close()

    assert replace_snapshot.call_count == 2

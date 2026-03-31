"""Tests for the cache-backed remote backend."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Protocol

import pytest
from typing_extensions import Self

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


class _ObservedLock:
    """Wrap a lock and signal when a second acquisition is attempted."""

    def __init__(
        self,
        lock: _LockLike,
        second_attempted: threading.Event,
    ) -> None:
        """Store the wrapped lock and contention signal."""
        self._lock = lock
        self._second_attempted = second_attempted
        self._attempts = 0
        self._attempts_lock = threading.Lock()

    def __enter__(self) -> Self:
        """Signal when a second caller tries to enter the lock."""
        with self._attempts_lock:
            self._attempts += 1
            if self._attempts == 2:
                self._second_attempted.set()
        self._lock.acquire()
        return self

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        """Release the wrapped lock."""
        del exc_type, exc, traceback
        self._lock.release()


class _LockLike(Protocol):
    """Small protocol for the lock methods this test wrapper needs."""

    def acquire(self) -> bool | None:
        """Acquire the wrapped lock."""

    def release(self) -> None:
        """Release the wrapped lock."""


def _patch_tracked_snapshot_replacement(
    mocker: MockerFixture,
    backend: RemoteIdeaBackend,
    *,
    first_started: threading.Event,
    second_attempted: threading.Event,
    allow_exit: threading.Event,
) -> dict[str, int]:
    """Patch sync internals and capture concurrent replacement attempts."""
    active_state = {"current": 0, "max": 0}
    active_lock = threading.Lock()
    mocker.patch.object(
        backend,
        "_sync_lock",
        _ObservedLock(backend._sync_lock, second_attempted),
    )

    def tracked_replace_snapshot(
        _repo: RemoteCacheRepository,
        _snapshot: object,
    ) -> None:
        with active_lock:
            active_state["current"] += 1
            active_state["max"] = max(
                active_state["max"],
                active_state["current"],
            )
            first_started.set()
        try:
            allow_exit.wait(timeout=1)
        finally:
            with active_lock:
                active_state["current"] -= 1

    mocker.patch.object(
        RemoteCacheRepository,
        "replace_snapshot",
        autospec=True,
        side_effect=tracked_replace_snapshot,
    )
    return active_state


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
    current = mocker.Mock(
        body="Old body",
        group=mocker.Mock(pk=7),
        updated_at=11,
    )
    current.tags.fetch_all.return_value = [
        mocker.Mock(name="tag-one"),
        mocker.Mock(name="tag-two"),
    ]
    current.tags.fetch_all.return_value[0].name = "tag-one"
    current.tags.fetch_all.return_value[1].name = "tag-two"
    updated = mocker.Mock(pk=5)
    renamed = mocker.Mock(name="renamed")

    mocker.patch.object(
        backend._cache_service,
        "get_idea_with_relations",
        return_value=current,
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

    update_call = update_idea.call_args
    assert update_call is not None
    assert update_call.args[0] == 5
    request = update_call.args[1]
    assert request.title == "Renamed title"
    assert request.body == "Old body"
    assert request.tags == ["tag-one", "tag-two"]
    assert request.group_pk == 7
    assert request.last_known_updated_at == 11
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
    first_started = threading.Event()
    second_attempted = threading.Event()
    allow_exit = threading.Event()
    active_state = _patch_tracked_snapshot_replacement(
        mocker,
        backend,
        first_started=first_started,
        second_attempted=second_attempted,
        allow_exit=allow_exit,
    )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_one = executor.submit(backend.sync_from_remote)
            assert first_started.wait(timeout=1)
            future_two = executor.submit(backend.sync_from_remote)

            assert second_attempted.wait(timeout=1)
            assert active_state["max"] == 1

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


def test_remote_backend_serializes_writes_with_snapshot_replacement(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Remote writes should wait for an in-flight sync to finish."""
    cache_db = get_db(str(tmp_path / "remote-cache.db"))
    backend = RemoteIdeaBackend(
        cache_db,
        default_group_name="default",
        api_client=mocker.Mock(),
    )
    first_started = threading.Event()
    second_attempted = threading.Event()
    allow_exit = threading.Event()
    _patch_tracked_snapshot_replacement(
        mocker,
        backend,
        first_started=first_started,
        second_attempted=second_attempted,
        allow_exit=allow_exit,
    )
    write_started = threading.Event()
    created_response = mocker.Mock(pk=123)
    created_idea = mocker.Mock(name="created_idea")
    mocker.patch.object(
        backend._api_client,
        "fetch_snapshot",
        return_value=object(),
    )

    def tracked_create_idea(*args: object, **kwargs: object) -> object:
        del args, kwargs
        write_started.set()
        return created_response

    mocker.patch.object(
        backend._api_client,
        "create_idea",
        side_effect=tracked_create_idea,
    )
    mocker.patch.object(backend._cache_repo, "upsert_idea")
    mocker.patch.object(
        backend,
        "_require_cached_idea",
        return_value=created_idea,
    )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            sync_future = executor.submit(backend.sync_from_remote)
            assert first_started.wait(timeout=1)

            write_future = executor.submit(
                backend.create_idea,
                "Concurrent idea",
                group_pk=1,
            )

            assert second_attempted.wait(timeout=1)
            assert not write_started.wait(timeout=0.1)

            allow_exit.set()
            sync_future.result()
            created = write_future.result()
    finally:
        cache_db.close()

    assert write_started.is_set()
    assert created is created_idea

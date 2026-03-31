"""Tests for remote backend sync and threading behavior."""

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


def _patch_tracked_remote_create(
    mocker: MockerFixture,
    backend: RemoteIdeaBackend,
) -> tuple[threading.Event, object]:
    """Patch create_idea so the test can observe when the write begins."""
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
    return write_started, created_idea


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


def test_remote_backend_sync_from_worker_thread_rejects_memory_cache() -> None:
    """Worker-thread sync should fail fast for in-memory caches."""
    cache_db = get_db(memory=True)
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

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(backend.sync_from_remote)
            with pytest.raises(
                RuntimeError,
                match=(
                    "Worker-thread sync requires a file-backed cache database"
                ),
            ):
                future.result()
    finally:
        cache_db.close()


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
    write_started, created_idea = _patch_tracked_remote_create(mocker, backend)

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

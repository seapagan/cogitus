"""Cache-backed remote backend implementation."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from sqliter import SqliterDB

from cogitus.api.schemas.request.idea import (
    IdeaCreateRequest,
    IdeaUpdateRequest,
)
from cogitus.backends.protocols import SyncingIdeaBackend
from cogitus.db import enable_wal_mode
from cogitus.repositories.remote_cache_repo import RemoteCacheRepository
from cogitus.services.idea_service import IdeaService

if TYPE_CHECKING:
    from cogitus.backends.api_client import RemoteAPIClient
    from cogitus.models.group import Group
    from cogitus.models.idea import Idea
    from cogitus.models.tag import Tag
    from cogitus.search import SearchResult


class RemoteIdeaBackend(SyncingIdeaBackend):
    """Use the HTTP API as the source of truth with a local SQLite cache."""

    def __init__(
        self,
        cache_db: SqliterDB,
        *,
        default_group_name: str,
        api_client: RemoteAPIClient,
    ) -> None:
        """Initialize the remote backend and its local cache service."""
        self._cache_db = cache_db
        self._api_client = api_client
        self._owner_thread_id = threading.get_ident()
        self._sync_lock = threading.Lock()
        self._cache_service = IdeaService(
            cache_db,
            default_group_name=default_group_name,
        )
        self._cache_repo = RemoteCacheRepository(
            cache_db,
            default_group_name=default_group_name,
        )

    @property
    def default_group_name(self) -> str:
        """Return the configured fallback group name."""
        return self._cache_service.default_group_name

    def create_idea(
        self,
        title: str,
        body: str = "",
        tags: list[str] | None = None,
        group_pk: int | None = None,
    ) -> Idea:
        """Create a remote idea and mirror it into the cache."""
        with self._sync_lock:
            created = self._api_client.create_idea(
                IdeaCreateRequest(
                    title=title,
                    body=body,
                    tags=tags or [],
                    group_pk=group_pk,
                )
            )
            self._cache_repo.upsert_idea(created)
            return self._require_cached_idea(created.pk)

    def update_idea(
        self,
        pk: int,
        title: str,
        body: str,
        tags: list[str] | None = None,
        group_pk: int | None = None,
    ) -> Idea | None:
        """Update a remote idea if the cached version is still current."""
        with self._sync_lock:
            current = self._cache_service.get_idea(pk)
            if current is None:
                return None

            updated = self._api_client.update_idea(
                pk,
                IdeaUpdateRequest(
                    title=title,
                    body=body,
                    tags=tags or [],
                    group_pk=group_pk,
                    last_known_updated_at=current.updated_at,
                ),
            )
            self._cache_repo.upsert_idea(updated)
            return self._require_cached_idea(updated.pk)

    def rename_idea(self, pk: int, title: str) -> Idea | None:
        """Rename a remote idea using the same stale-write protection."""
        current_with_relations = self._cache_service.get_idea_with_relations(pk)
        if current_with_relations is None:
            return None
        return self.update_idea(
            pk,
            title=title,
            body=current_with_relations.body,
            tags=[tag.name for tag in current_with_relations.tags.fetch_all()],
            group_pk=current_with_relations.group.pk,
        )

    def delete_idea(self, pk: int) -> None:
        """Delete a remote idea and remove it from the cache."""
        with self._sync_lock:
            self._api_client.delete_idea(pk)
            self._cache_repo.delete_idea(pk)

    def get_idea(self, pk: int) -> Idea | None:
        """Fetch one cached idea."""
        return self._cache_service.get_idea(pk)

    def list_tags_in_use(self) -> list[Tag]:
        """Return tags linked to at least one cached idea."""
        return self._cache_service.list_tags_in_use()

    def list_tags_with_usage(self) -> list[tuple[Tag, int]]:
        """Return cached tags with usage counts."""
        return self._cache_service.list_tags_with_usage()

    def get_idea_cursor_position(self, idea_pk: int) -> int | None:
        """Return the client-local cursor position for an idea."""
        return self._cache_service.get_idea_cursor_position(idea_pk)

    def set_idea_cursor_position(self, idea_pk: int, position: int) -> None:
        """Persist the client-local cursor position for an idea."""
        self._cache_service.set_idea_cursor_position(idea_pk, position)

    def list_groups(self) -> list[Group]:
        """List cached groups."""
        return self._cache_service.list_groups()

    def get_group(self, pk: int) -> Group | None:
        """Fetch a cached group."""
        return self._cache_service.get_group(pk)

    def create_group(self, name: str) -> Group:
        """Create a remote group and mirror it into the cache."""
        with self._sync_lock:
            created = self._api_client.create_group(name)
            self._cache_repo.upsert_group(created)
            return self._require_cached_group(created.pk)

    def rename_group(self, pk: int, name: str) -> Group | None:
        """Rename a remote group and refresh cached search metadata."""
        with self._sync_lock:
            current = self._cache_service.get_group(pk)
            if current is None:
                return None
            renamed = self._api_client.rename_group(pk, name)
            self._cache_repo.upsert_group(renamed)
            self._cache_repo.rebuild_search_index()
            return self._require_cached_group(renamed.pk)

    def has_ideas_in_group(self, group_pk: int) -> bool:
        """Return whether the cached group contains ideas."""
        return self._cache_service.has_ideas_in_group(group_pk)

    def list_ideas_grouped(
        self,
        query: str | None = None,
    ) -> list[tuple[Group, list[Idea]]]:
        """Return cached grouped ideas for the main list."""
        return self._cache_service.list_ideas_grouped(query)

    def search_results(self, query: str) -> list[SearchResult]:
        """Return cached search results."""
        return self._cache_service.search_results(query)

    def delete_group(
        self,
        group_pk: int,
        move_to_group_pk: int | None = None,
    ) -> None:
        """Delete a remote group and mirror the change into the cache."""
        with self._sync_lock:
            self._api_client.delete_group(
                group_pk,
                move_to_group_pk=move_to_group_pk,
            )
            self._cache_repo.delete_group(
                group_pk,
                move_to_group_pk=move_to_group_pk,
            )

    def sync_from_remote(self) -> None:
        """Replace the local cache with the latest remote snapshot."""
        with self._sync_lock:
            snapshot = self._api_client.fetch_snapshot()
            if (
                self._cache_db.is_memory
                or threading.get_ident() == self._owner_thread_id
            ):
                self._cache_repo.replace_snapshot(snapshot)
                return

            worker_db = self._build_worker_cache_db()
            worker_repo = RemoteCacheRepository(
                worker_db,
                default_group_name=self.default_group_name,
            )
            try:
                worker_repo.replace_snapshot(snapshot)
            finally:
                worker_db.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._api_client.close()

    def _build_worker_cache_db(self) -> SqliterDB:
        """Open a fresh file-backed cache DB for worker-thread sync."""
        if self._cache_db.is_memory:
            msg = "Worker-thread sync requires a file-backed cache database"
            raise RuntimeError(msg)
        db_path = self._cache_db.filename
        if db_path is None:
            msg = "Remote cache database path is unavailable"
            raise RuntimeError(msg)

        worker_db = SqliterDB(db_path)
        enable_wal_mode(worker_db)
        return worker_db

    def _require_cached_group(self, group_pk: int) -> Group:
        """Return a cached group after an API write."""
        group = self._cache_service.get_group(group_pk)
        if group is None:
            msg = f"Group {group_pk} not found in cache"
            raise RuntimeError(msg)
        return group

    def _require_cached_idea(self, idea_pk: int) -> Idea:
        """Return a cached idea after an API write."""
        idea = self._cache_service.get_idea(idea_pk)
        if idea is None:
            msg = f"Idea {idea_pk} not found in cache"
            raise RuntimeError(msg)
        return idea

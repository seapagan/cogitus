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
from cogitus.search.backend import FtsSearchBackend
from cogitus.services.idea_service import IdeaService

if TYPE_CHECKING:
    import sqlite3

    from cogitus.api.schemas.response.group import GroupResponse
    from cogitus.api.schemas.response.idea import IdeaResponse
    from cogitus.api.schemas.response.tag import TagResponse
    from cogitus.backends.api_client import RemoteAPIClient
    from cogitus.backends.types import RemoteSnapshot
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
        self._cache_service = IdeaService(
            cache_db,
            default_group_name=default_group_name,
        )
        self._search_backend = FtsSearchBackend(cache_db)

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
        created = self._api_client.create_idea(
            IdeaCreateRequest(
                title=title,
                body=body,
                tags=tags or [],
                group_pk=group_pk,
            )
        )
        self._upsert_idea(created)
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
        self._upsert_idea(updated)
        return self._require_cached_idea(updated.pk)

    def rename_idea(self, pk: int, title: str) -> Idea | None:
        """Rename a remote idea using the same stale-write protection."""
        current = self._cache_service.get_idea(pk)
        if current is None:
            return None
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
        self._api_client.delete_idea(pk)
        self._delete_cached_idea(pk)

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
        created = self._api_client.create_group(name)
        self._upsert_group(created)
        return self._require_cached_group(created.pk)

    def rename_group(self, pk: int, name: str) -> Group | None:
        """Rename a remote group and refresh cached search metadata."""
        current = self._cache_service.get_group(pk)
        if current is None:
            return None
        renamed = self._api_client.rename_group(pk, name)
        self._upsert_group(renamed)
        self._search_backend.rebuild()
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
        self._api_client.delete_group(
            group_pk,
            move_to_group_pk=move_to_group_pk,
        )
        self._delete_cached_group(
            group_pk,
            move_to_group_pk=move_to_group_pk,
        )

    def sync_from_remote(self) -> None:
        """Replace the local cache with the latest remote snapshot."""
        snapshot = self._api_client.fetch_snapshot()
        if (
            self._cache_db.is_memory
            or threading.get_ident() == self._owner_thread_id
        ):
            self._replace_cache(
                snapshot,
                db=self._cache_db,
                cache_service=self._cache_service,
                search_backend=self._search_backend,
            )
            return

        worker_db = self._build_worker_cache_db()
        worker_service = IdeaService(
            worker_db,
            default_group_name=self.default_group_name,
        )
        worker_search_backend = FtsSearchBackend(worker_db)
        try:
            self._replace_cache(
                snapshot,
                db=worker_db,
                cache_service=worker_service,
                search_backend=worker_search_backend,
            )
        finally:
            worker_db.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._api_client.close()

    def _replace_cache(
        self,
        snapshot: RemoteSnapshot,
        *,
        db: SqliterDB,
        cache_service: IdeaService,
        search_backend: FtsSearchBackend,
    ) -> None:
        """Replace the entire local cache with the provided snapshot."""
        cursor_positions = self._snapshot_cursor_positions(db)
        with db.connect() as conn:
            self._clear_cache_tables(conn)
            self._insert_snapshot_groups(conn, snapshot)
            self._insert_snapshot_tags(conn, snapshot)
            self._insert_snapshot_ideas(conn, snapshot)
            self._insert_snapshot_idea_tags(conn, snapshot)
            conn.commit()
        search_backend.rebuild()
        self._restore_cursor_positions(
            cache_service,
            cursor_positions,
            valid_idea_pks={idea.pk for idea in snapshot.ideas},
        )

    @staticmethod
    def _clear_cache_tables(conn: sqlite3.Connection) -> None:
        """Delete all cached rows before repopulating the local snapshot."""
        conn.execute("DELETE FROM idea_cursor_states;")
        conn.execute("DELETE FROM ideas_tags;")
        conn.execute("DELETE FROM ideas;")
        conn.execute("DELETE FROM groups;")
        conn.execute("DELETE FROM tags;")

    @staticmethod
    def _insert_snapshot_groups(
        conn: sqlite3.Connection,
        snapshot: RemoteSnapshot,
    ) -> None:
        """Insert all groups from a remote snapshot."""
        conn.executemany(
            """
            INSERT INTO groups (pk, created_at, updated_at, name)
            VALUES (?, ?, ?, ?);
            """,
            [
                (
                    group.pk,
                    group.created_at,
                    group.updated_at,
                    group.name,
                )
                for group in snapshot.groups
            ],
        )

    @staticmethod
    def _insert_snapshot_tags(
        conn: sqlite3.Connection,
        snapshot: RemoteSnapshot,
    ) -> None:
        """Insert all tags from a remote snapshot."""
        conn.executemany(
            """
            INSERT INTO tags (pk, created_at, updated_at, name)
            VALUES (?, ?, ?, ?);
            """,
            [
                (
                    tag.pk,
                    tag.created_at,
                    tag.updated_at,
                    tag.name,
                )
                for tag in snapshot.tags
            ],
        )

    @staticmethod
    def _insert_snapshot_ideas(
        conn: sqlite3.Connection,
        snapshot: RemoteSnapshot,
    ) -> None:
        """Insert all ideas from a remote snapshot."""
        conn.executemany(
            """
            INSERT INTO ideas (
                pk,
                created_at,
                updated_at,
                title,
                body,
                group_id
            )
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            [
                (
                    idea.pk,
                    idea.created_at,
                    idea.updated_at,
                    idea.title,
                    idea.body,
                    idea.group.pk,
                )
                for idea in snapshot.ideas
            ],
        )

    @staticmethod
    def _insert_snapshot_idea_tags(
        conn: sqlite3.Connection,
        snapshot: RemoteSnapshot,
    ) -> None:
        """Insert all idea-to-tag links from a remote snapshot."""
        conn.executemany(
            """
            INSERT INTO ideas_tags (ideas_pk, tags_pk)
            VALUES (?, ?);
            """,
            [(idea.pk, tag.pk) for idea in snapshot.ideas for tag in idea.tags],
        )

    def _upsert_group(self, group: GroupResponse) -> None:
        """Insert or replace one cached group row."""
        with self._cache_db.connect() as conn:
            conn.execute(
                """
                INSERT INTO groups (pk, created_at, updated_at, name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(pk) DO UPDATE SET
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    name = excluded.name;
                """,
                (
                    group.pk,
                    group.created_at,
                    group.updated_at,
                    group.name,
                ),
            )
            conn.commit()

    def _upsert_tag(self, tag: TagResponse) -> None:
        """Insert or replace one cached tag row."""
        with self._cache_db.connect() as conn:
            conn.execute(
                """
                INSERT INTO tags (pk, created_at, updated_at, name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(pk) DO UPDATE SET
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    name = excluded.name;
                """,
                (
                    tag.pk,
                    tag.created_at,
                    tag.updated_at,
                    tag.name,
                ),
            )
            conn.commit()

    def _upsert_idea(self, idea: IdeaResponse) -> None:
        """Insert or replace one cached idea and its relationships."""
        self._upsert_group(idea.group)
        for tag in idea.tags:
            self._upsert_tag(tag)
        with self._cache_db.connect() as conn:
            conn.execute(
                """
                INSERT INTO ideas (
                    pk,
                    created_at,
                    updated_at,
                    title,
                    body,
                    group_id
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(pk) DO UPDATE SET
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    title = excluded.title,
                    body = excluded.body,
                    group_id = excluded.group_id;
                """,
                (
                    idea.pk,
                    idea.created_at,
                    idea.updated_at,
                    idea.title,
                    idea.body,
                    idea.group.pk,
                ),
            )
            conn.execute(
                "DELETE FROM ideas_tags WHERE ideas_pk = ?;",
                (idea.pk,),
            )
            conn.executemany(
                """
                INSERT INTO ideas_tags (ideas_pk, tags_pk)
                VALUES (?, ?);
                """,
                [(idea.pk, tag.pk) for tag in idea.tags],
            )
            conn.commit()
        self._search_backend.upsert_idea(idea.pk)

    def _delete_cached_idea(self, idea_pk: int) -> None:
        """Delete one cached idea and its cursor state."""
        with self._cache_db.connect() as conn:
            conn.execute(
                "DELETE FROM idea_cursor_states WHERE idea_id = ?;",
                (idea_pk,),
            )
            conn.execute(
                "DELETE FROM ideas_tags WHERE ideas_pk = ?;",
                (idea_pk,),
            )
            conn.execute("DELETE FROM ideas WHERE pk = ?;", (idea_pk,))
            conn.commit()
        self._search_backend.delete_idea(idea_pk)

    def _delete_cached_group(
        self,
        group_pk: int,
        *,
        move_to_group_pk: int | None,
    ) -> None:
        """Delete one cached group and mirror any local group move."""
        target_group_pk = move_to_group_pk
        if target_group_pk is None:
            for group in self._cache_service.list_groups():
                if group.name == self.default_group_name:
                    target_group_pk = group.pk
                    break
        with self._cache_db.connect() as conn:
            if target_group_pk is not None:
                conn.execute(
                    """
                    UPDATE ideas
                    SET group_id = ?
                    WHERE group_id = ?;
                    """,
                    (target_group_pk, group_pk),
                )
            conn.execute("DELETE FROM groups WHERE pk = ?;", (group_pk,))
            conn.commit()
        self._search_backend.rebuild()

    def _snapshot_cursor_positions(self, db: SqliterDB) -> dict[int, int]:
        """Capture client-local cursor positions before a full cache swap."""
        rows = db.connect().execute(
            """
            SELECT idea_id, body_cursor_position
            FROM idea_cursor_states;
            """
        )
        return {int(row[0]): int(row[1]) for row in rows.fetchall()}

    def _restore_cursor_positions(
        self,
        cache_service: IdeaService,
        cursor_positions: dict[int, int],
        *,
        valid_idea_pks: set[int],
    ) -> None:
        """Restore cursor positions for ideas that still exist remotely."""
        for idea_pk, position in cursor_positions.items():
            if idea_pk in valid_idea_pks:
                cache_service.set_idea_cursor_position(idea_pk, position)

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
        worker_db.connect().execute("PRAGMA journal_mode=WAL;")
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

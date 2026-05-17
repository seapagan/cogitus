"""Database connection factory for Cogitus.

Raw SQL remains intentional in this module for SQLite-specific PRAGMA,
schema-inspection, and migration operations that are outside sqliter-py's
documented ORM/query surface.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqliter import SqliterDB
from sqliter.exceptions import SqliterError

from cogitus.config import normalize_default_group_name
from cogitus.constants import DEFAULT_GROUP_NAME
from cogitus.hashing import idea_detail_hash
from cogitus.models.dataset_state import DatasetState
from cogitus.models.group import Group
from cogitus.models.idea import Idea
from cogitus.models.idea_cursor_state import IdeaCursorState
from cogitus.models.idea_scroll_state import IdeaScrollState
from cogitus.models.tag import Tag
from cogitus.repositories.dataset_state_repo import DatasetStateRepository
from cogitus.search.backend import FtsSearchBackend, ensure_search_tables

DEFAULT_DB_PATH = "~/.config/cogitus/cogitus.db"


def _ensure_default_group(db: SqliterDB, default_group_name: str) -> int:
    """Ensure the default group exists and return its primary key."""
    group = db.select(Group).filter(name=default_group_name).fetch_one()
    if group is None:
        group = db.insert(Group(name=default_group_name))
    return group.pk


def enable_wal_mode(db: SqliterDB) -> None:
    """Enable WAL journaling for file-backed SQLite databases."""
    if db.is_memory:
        return
    result = db.connect().execute("PRAGMA journal_mode=WAL;").fetchone()
    mode = "" if result is None else str(result[0]).lower()
    if mode != "wal":
        msg = (
            "Failed to enable WAL mode; "
            f"SQLite reported {mode or 'unknown'} instead"
        )
        raise RuntimeError(msg)


def _column_exists(db: SqliterDB, table_name: str, column_name: str) -> bool:
    """Return True if a column exists in the given table."""
    if not table_name.isidentifier():
        msg = f"Invalid table name: {table_name}"
        raise ValueError(msg)
    result = db.connect().execute(f"PRAGMA table_info({table_name});")
    return any(str(row[1]) == column_name for row in result.fetchall())


def _migrate_ideas_group_fk(db: SqliterDB, default_group_pk: int) -> None:
    """Add ideas.group_id and backfill existing rows when missing."""
    with db.connect() as conn:
        if not _column_exists(db, "ideas", "group_id"):
            conn.execute("ALTER TABLE ideas ADD COLUMN group_id INTEGER;")
        conn.execute(
            """
            UPDATE ideas
            SET group_id = ?
            WHERE group_id IS NULL
               OR NOT EXISTS (
                    SELECT 1
                    FROM groups
                    WHERE groups.pk = ideas.group_id
               );
            """,
            (default_group_pk,),
        )
        conn.commit()


def _migrate_idea_detail_hash(db: SqliterDB) -> None:
    """Add and backfill ideas.detail_hash when missing or empty."""
    with db.connect() as conn:
        if not _column_exists(db, "ideas", "detail_hash"):
            conn.execute(
                "ALTER TABLE ideas "
                "ADD COLUMN detail_hash TEXT NOT NULL DEFAULT '';"
            )
        conn.execute(
            "UPDATE ideas SET detail_hash = '' WHERE detail_hash IS NULL;"
        )
        tag_table_exists = "ideas_tags" in db.table_names
        idea_rows = conn.execute(
            """
            SELECT pk, title, body, created_at, updated_at
            FROM ideas
            WHERE detail_hash = '';
            """
        ).fetchall()
        for idea_pk, title, body, created_at, updated_at in idea_rows:
            if tag_table_exists:
                tag_rows = conn.execute(
                    """
                    SELECT tags.name
                    FROM tags
                    INNER JOIN ideas_tags
                        ON ideas_tags.tags_pk = tags.pk
                    WHERE ideas_tags.ideas_pk = ?;
                    """,
                    (idea_pk,),
                ).fetchall()
            else:
                tag_rows = []
            conn.execute(
                "UPDATE ideas SET detail_hash = ? WHERE pk = ?;",
                (
                    idea_detail_hash(
                        title="" if title is None else str(title),
                        body="" if body is None else str(body),
                        tag_names=[
                            "" if row[0] is None else str(row[0])
                            for row in tag_rows
                        ],
                        created_at=int(created_at),
                        updated_at=int(updated_at),
                    ),
                    idea_pk,
                ),
            )
        conn.commit()


def get_db(
    db_path: str = DEFAULT_DB_PATH,
    *,
    memory: bool = False,
    default_group_name: str = DEFAULT_GROUP_NAME,
) -> SqliterDB:
    """Create and return a configured database connection.

    Ensures the parent directory exists and all tables are created.

    Args:
        db_path: Path to the SQLite database file (ignored if memory=True).
        memory: If True, use an in-memory database.
        default_group_name: Canonical fallback group name.

    Returns:
        A connected SqliterDB instance with all tables ready.
    """
    if memory:
        db = SqliterDB(memory=True)
    else:
        expanded = Path(db_path).expanduser()
        expanded.parent.mkdir(parents=True, exist_ok=True)
        db = SqliterDB(str(expanded))
        try:
            enable_wal_mode(db)
        except (RuntimeError, SqliterError, sqlite3.Error):
            db.close()
            raise

    normalized_default_group_name = normalize_default_group_name(
        default_group_name
    )

    db.create_table(Tag)
    db.create_table(Group)
    default_group_pk = _ensure_default_group(
        db,
        normalized_default_group_name,
    )
    ideas_existed = "ideas" in db.table_names
    if ideas_existed:
        _migrate_ideas_group_fk(db, default_group_pk)
    db.create_table(Idea)
    db.create_table(IdeaCursorState)
    db.create_table(IdeaScrollState)
    if not ideas_existed:
        _migrate_ideas_group_fk(db, default_group_pk)
    _migrate_idea_detail_hash(db)
    db.create_table(DatasetState)
    DatasetStateRepository(db).get_hash()
    ensure_search_tables(db)
    FtsSearchBackend(db).rebuild()
    return db

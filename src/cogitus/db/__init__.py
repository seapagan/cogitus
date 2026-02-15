"""Database connection factory for Cogitus."""

from __future__ import annotations

from pathlib import Path

from sqliter import SqliterDB

from cogitus.config import normalize_default_group_name
from cogitus.constants import DEFAULT_GROUP_NAME
from cogitus.models.group import Group
from cogitus.models.idea import Idea
from cogitus.models.idea_cursor_state import IdeaCursorState
from cogitus.models.tag import Tag

DEFAULT_DB_PATH = "~/.config/cogitus/cogitus.db"


def _ensure_default_group(db: SqliterDB, default_group_name: str) -> int:
    """Ensure the default group exists and return its primary key."""
    group = db.select(Group).filter(name=default_group_name).fetch_one()
    if group is None:
        group = db.insert(Group(name=default_group_name))
    return group.pk


def _column_exists(db: SqliterDB, table_name: str, column_name: str) -> bool:
    """Return True if a column exists in the given table."""
    if not table_name.isidentifier():
        msg = f"Invalid table name: {table_name}"
        raise ValueError(msg)
    result = db.connect().execute(f"PRAGMA table_info({table_name});")
    return any(str(row[1]) == column_name for row in result.fetchall())


def _table_exists(db: SqliterDB, table_name: str) -> bool:
    """Return True if the table exists."""
    row = (
        db.connect()
        .execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?;",
            (table_name,),
        )
        .fetchone()
    )
    return row is not None


def _index_exists(db: SqliterDB, index_name: str) -> bool:
    """Return True if the index exists."""
    row = (
        db.connect()
        .execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name = ?;",
            (index_name,),
        )
        .fetchone()
    )
    return row is not None


def _migrate_ideas_group_fk(db: SqliterDB, default_group_pk: int) -> None:
    """Add ideas.group_id and backfill existing rows when missing."""
    with db.connect() as conn:
        column_added = False
        if not _column_exists(db, "ideas", "group_id"):
            conn.execute("ALTER TABLE ideas ADD COLUMN group_id INTEGER;")
            column_added = True
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
        changes_row = conn.execute("SELECT changes();").fetchone()
        repaired_rows = int(changes_row[0]) if changes_row is not None else 0
        index_missing = not _index_exists(
            db,
            "idx_ideas_group_id",
        )
        if column_added or index_missing or repaired_rows > 0:
            # Rebuild index only when migration actually changed state.
            conn.execute("DROP INDEX IF EXISTS idx_ideas_group_id;")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ideas_group_id "
                "ON ideas (group_id);"
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
        db.connect().execute("PRAGMA journal_mode=WAL;")

    normalized_default_group_name = normalize_default_group_name(
        default_group_name
    )

    db.create_table(Tag)
    db.create_table(Group)
    default_group_pk = _ensure_default_group(
        db,
        normalized_default_group_name,
    )
    ideas_existed = _table_exists(db, "ideas")
    if ideas_existed:
        _migrate_ideas_group_fk(db, default_group_pk)
    db.create_table(Idea)
    db.create_table(IdeaCursorState)
    if not ideas_existed:
        _migrate_ideas_group_fk(db, default_group_pk)
    return db

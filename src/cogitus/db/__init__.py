"""Database connection factory for Cogitus."""

from __future__ import annotations

from pathlib import Path

from sqliter import SqliterDB

from cogitus.models.idea import Idea
from cogitus.models.tag import Tag

DEFAULT_DB_PATH = "~/.config/cogitus/cogitus.db"


def get_db(
    db_path: str = DEFAULT_DB_PATH, *, memory: bool = False
) -> SqliterDB:
    """Create and return a configured database connection.

    Ensures the parent directory exists and all tables are created.

    Args:
        db_path: Path to the SQLite database file (ignored if memory=True).
        memory: If True, use an in-memory database.

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

    db.create_table(Tag)
    db.create_table(Idea)
    return db

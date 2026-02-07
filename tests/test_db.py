"""Tests for database initialization helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.db import get_db
from cogitus.models.idea import Idea
from cogitus.models.tag import Tag

if TYPE_CHECKING:
    from pathlib import Path


def test_get_db_memory_creates_tables() -> None:
    """In-memory database should be initialized with required tables."""
    db = get_db(memory=True)
    try:
        tag = db.insert(Tag(name="python"))
        idea = db.insert(Idea(title="Test"))
        idea.tags.add(tag)
        assert tag.pk > 0
        assert idea.pk > 0
    finally:
        db.close()


def test_get_db_file_path_creates_parent(tmp_path: Path) -> None:
    """File database path should create its parent directory automatically."""
    db_file = tmp_path / "nested" / "cogitus.db"
    db = get_db(str(db_file))
    try:
        assert db_file.parent.exists()
        assert db_file.exists()
    finally:
        db.close()


def test_get_db_file_enables_wal_mode(tmp_path: Path) -> None:
    """File-backed database should enable WAL journal mode."""
    db_file = tmp_path / "nested" / "cogitus.db"
    db = get_db(str(db_file))
    try:
        result = db.connect().execute("PRAGMA journal_mode;").fetchone()
        assert result is not None
        assert str(result[0]).lower() == "wal"
    finally:
        db.close()

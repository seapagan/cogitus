"""Tests for database initialization helpers."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

from cogitus.db import _column_exists, get_db
from cogitus.models.group import Group
from cogitus.models.idea import Idea
from cogitus.models.idea_cursor_state import IdeaCursorState
from cogitus.models.tag import Tag

if TYPE_CHECKING:
    from pathlib import Path


def test_get_db_memory_creates_tables() -> None:
    """In-memory database should be initialized with required tables."""
    db = get_db(memory=True)
    try:
        tag = db.insert(Tag(name="python"))
        group = db.select(Group).filter(name="default").fetch_one()
        assert group is not None
        idea = db.insert(Idea(title="Test", group=group))
        idea.tags.add(tag)
        state = db.insert(IdeaCursorState(idea=idea, body_cursor_position=3))
        assert tag.pk > 0
        assert idea.pk > 0
        assert state.pk > 0
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


def test_get_db_backfills_group_id_for_existing_ideas(tmp_path: Path) -> None:
    """Existing ideas should be migrated into default group."""
    db_file = tmp_path / "legacy" / "cogitus.db"
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file))
    try:
        conn.execute(
            """
            CREATE TABLE ideas (
                pk INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT ''
            );
            """
        )
        conn.execute(
            "INSERT INTO ideas (title, body) VALUES (?, ?)",
            ("Legacy", ""),
        )
        conn.commit()
    finally:
        conn.close()

    migrated = get_db(str(db_file))
    try:
        migrated_default = (
            migrated.select(Group).filter(name="default").fetch_one()
        )
        assert migrated_default is not None
        ideas = migrated.select(Idea).fetch_all()
        assert len(ideas) == 1
        assert ideas[0].group.pk == migrated_default.pk
    finally:
        migrated.close()


def test_get_db_backfills_null_group_id_for_existing_column(
    tmp_path: Path,
) -> None:
    """Rows with NULL group_id should be repaired to default group."""
    db_file = tmp_path / "legacy-null-group" / "cogitus.db"
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file))
    try:
        conn.execute(
            """
            CREATE TABLE ideas (
                pk INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                group_id INTEGER
            );
            """
        )
        conn.execute(
            "INSERT INTO ideas (title, body, group_id) VALUES (?, ?, ?)",
            ("Legacy NULL group", "", None),
        )
        conn.commit()
    finally:
        conn.close()

    migrated = get_db(str(db_file))
    try:
        migrated_default = (
            migrated.select(Group).filter(name="default").fetch_one()
        )
        assert migrated_default is not None
        ideas = migrated.select(Idea).fetch_all()
        assert len(ideas) == 1
        assert ideas[0].group.pk == migrated_default.pk
    finally:
        migrated.close()


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


def test_column_exists_rejects_invalid_identifier() -> None:
    """Invalid table names should be rejected before SQL execution."""
    db = get_db(memory=True)
    try:
        with pytest.raises(ValueError, match="Invalid table name"):
            _column_exists(db, "ideas;drop", "group_id")
    finally:
        db.close()

"""Tests for database initialization helpers."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

from cogitus.db import _column_exists, enable_wal_mode, get_db
from cogitus.models.group import Group
from cogitus.models.idea import Idea
from cogitus.models.idea_cursor_state import IdeaCursorState
from cogitus.models.tag import Tag

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from pytest_mock import MockerFixture


def _index_names(db_path: Path, table_name: str) -> set[str]:
    """Return all index names currently defined for a table."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(f"PRAGMA index_list({table_name});").fetchall()
    finally:
        conn.close()
    return {str(row[1]) for row in rows}


def _create_legacy_ideas_db(
    db_path: Path,
    *,
    idea_rows: Sequence[tuple[str, str, int | None]],
    group_rows: Sequence[tuple[int, str]] = (),
) -> None:
    """Create a legacy ideas schema with optional groups and seeded rows."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        if group_rows:
            conn.execute(
                """
                CREATE TABLE groups (
                    pk INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                    name TEXT NOT NULL UNIQUE
                );
                """
            )
            conn.executemany(
                "INSERT INTO groups (pk, name) VALUES (?, ?)",
                group_rows,
            )
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
        conn.executemany(
            "INSERT INTO ideas (title, body, group_id) VALUES (?, ?, ?)",
            idea_rows,
        )
        conn.commit()
    finally:
        conn.close()


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


def test_get_db_memory_creates_configured_default_group() -> None:
    """In-memory DB should create configured default group."""
    db = get_db(memory=True, default_group_name="Inbox")
    try:
        group = db.select(Group).filter(name="inbox").fetch_one()
        assert group is not None
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


def test_get_db_initializes_missing_ideas_table_in_partial_schema(
    tmp_path: Path,
) -> None:
    """Partial legacy schemas without ideas should still initialize cleanly."""
    db_file = tmp_path / "partial-schema" / "cogitus.db"
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file))
    try:
        conn.execute(
            """
            CREATE TABLE groups (
                pk INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                name TEXT NOT NULL UNIQUE
            );
            """
        )
        conn.execute(
            "INSERT INTO groups (name) VALUES (?)",
            ("existing",),
        )
        conn.commit()
    finally:
        conn.close()

    migrated = get_db(str(db_file))
    try:
        default_group = (
            migrated.select(Group).filter(name="default").fetch_one()
        )
        assert default_group is not None
        idea = migrated.insert(
            Idea(title="Partial schema works", group=default_group)
        )
        groups = migrated.select(Group).fetch_all()
        group_names = {group.name for group in groups}

        assert idea.group is not None
        assert idea.group.name == "default"
        assert group_names == {"default", "existing"}
    finally:
        migrated.close()


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
        assert "idx_ideas_group_id" in _index_names(db_file, "ideas")
    finally:
        migrated.close()


def test_get_db_backfills_null_group_id_for_existing_column(
    tmp_path: Path,
) -> None:
    """Rows with NULL group_id should be repaired to default group."""
    db_file = tmp_path / "legacy-null-group" / "cogitus.db"
    _create_legacy_ideas_db(
        db_file,
        idea_rows=(("Legacy NULL group", "", None),),
    )

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


def test_get_db_ensures_group_index_when_legacy_rows_need_no_repair(
    tmp_path: Path,
) -> None:
    """Legacy ideas with valid group IDs should still get the FK index."""
    db_file = tmp_path / "legacy-valid-group" / "cogitus.db"
    _create_legacy_ideas_db(
        db_file,
        group_rows=((1, "existing"),),
        idea_rows=(("Legacy valid group", "", 1),),
    )

    migrated = get_db(str(db_file))
    try:
        groups = migrated.select(Group).fetch_all()
        group_names = {group.name for group in groups}
        ideas = migrated.select(Idea).fetch_all()

        assert len(ideas) == 1
        assert ideas[0].group is not None
        assert ideas[0].group.name == "existing"
        assert group_names == {"default", "existing"}
        assert "idx_ideas_group_id" in _index_names(db_file, "ideas")
    finally:
        migrated.close()


def test_get_db_backfills_legacy_ideas_to_configured_default_group(
    tmp_path: Path,
) -> None:
    """Legacy rows should be repaired into configured fallback group."""
    db_file = tmp_path / "legacy-custom-default" / "cogitus.db"
    _create_legacy_ideas_db(
        db_file,
        idea_rows=(("Legacy NULL group", "", None),),
    )

    migrated = get_db(str(db_file), default_group_name="inbox")
    try:
        migrated_default = (
            migrated.select(Group).filter(name="inbox").fetch_one()
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


def test_enable_wal_mode_is_noop_for_memory_db() -> None:
    """In-memory databases should skip the WAL PRAGMA helper."""
    db = get_db(memory=True)
    try:
        enable_wal_mode(db)
        result = db.connect().execute("PRAGMA journal_mode;").fetchone()
        assert result is not None
        assert str(result[0]).lower() == "memory"
    finally:
        db.close()


def test_enable_wal_mode_raises_when_sqlite_keeps_prior_mode(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """File-backed DBs should fail clearly when WAL setup is refused."""
    db = get_db(str(tmp_path / "wal-refused.db"))
    try:
        fake_connection = mocker.Mock()
        fake_connection.execute.return_value.fetchone.return_value = ("delete",)
        mocker.patch.object(db, "connect", return_value=fake_connection)

        with pytest.raises(
            RuntimeError,
            match="Failed to enable WAL mode; SQLite reported delete instead",
        ):
            enable_wal_mode(db)
    finally:
        db.close()


def test_get_db_closes_db_when_wal_initialization_fails(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """File-backed DBs should close when WAL setup fails during init."""
    close_spy = mocker.patch("cogitus.db.SqliterDB.close", autospec=True)
    mocker.patch(
        "cogitus.db.enable_wal_mode",
        side_effect=RuntimeError("wal init failed"),
    )

    with pytest.raises(RuntimeError, match="wal init failed"):
        get_db(str(tmp_path / "wal-init-failed.db"))

    close_spy.assert_called_once()


def test_column_exists_rejects_invalid_identifier() -> None:
    """Invalid table names should be rejected before SQL execution."""
    db = get_db(memory=True)
    try:
        with pytest.raises(ValueError, match="Invalid table name"):
            _column_exists(db, "ideas;drop", "group_id")
    finally:
        db.close()

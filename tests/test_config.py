"""Tests for application settings configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.config import AppSettings, get_settings

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_get_settings_returns_singleton(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_settings should return the same singleton instance."""
    monkeypatch.setattr(
        "simple_toml_settings.settings.xdg_config_home",
        lambda: tmp_path,
    )
    AppSettings._instances.clear()

    first = get_settings()
    second = get_settings()

    assert first is second


def test_settings_persist_last_viewed_pk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings should persist and reload the last viewed idea primary key."""
    monkeypatch.setattr(
        "simple_toml_settings.settings.xdg_config_home",
        lambda: tmp_path,
    )
    AppSettings._instances.clear()

    settings = get_settings()
    settings.last_viewed_idea_pk = 42
    settings.save()

    AppSettings._instances.clear()
    loaded = get_settings()

    assert loaded.last_viewed_idea_pk == 42


def test_settings_persist_edit_body_cursor_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings should persist and reload edit cursor mode."""
    monkeypatch.setattr(
        "simple_toml_settings.settings.xdg_config_home",
        lambda: tmp_path,
    )
    AppSettings._instances.clear()

    settings = get_settings()
    settings.edit_body_cursor_mode = "end"
    settings.save()

    AppSettings._instances.clear()
    loaded = get_settings()

    assert loaded.edit_body_cursor_mode == "end"

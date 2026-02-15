"""Tests for application settings configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.config import (
    AppSettings,
    EditBodyCursorMode,
    NewIdeaGroupMode,
    get_settings,
    normalize_default_group_name,
    normalize_edit_body_cursor_mode,
    normalize_new_idea_group_mode,
)

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
    settings.edit_body_cursor_mode = EditBodyCursorMode.END.value
    settings.save()

    AppSettings._instances.clear()
    loaded = get_settings()

    assert loaded.edit_body_cursor_mode == EditBodyCursorMode.END.value


def test_settings_persist_new_idea_group_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings should persist and reload new-idea group mode."""
    monkeypatch.setattr(
        "simple_toml_settings.settings.xdg_config_home",
        lambda: tmp_path,
    )
    AppSettings._instances.clear()

    settings = get_settings()
    settings.new_idea_group_mode = NewIdeaGroupMode.DEFAULT_GROUP.value
    settings.save()

    AppSettings._instances.clear()
    loaded = get_settings()

    assert loaded.new_idea_group_mode == NewIdeaGroupMode.DEFAULT_GROUP.value


def test_settings_persist_default_group_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings should persist and reload default group name."""
    monkeypatch.setattr(
        "simple_toml_settings.settings.xdg_config_home",
        lambda: tmp_path,
    )
    AppSettings._instances.clear()

    settings = get_settings()
    settings.default_group_name = "inbox"
    settings.save()

    AppSettings._instances.clear()
    loaded = get_settings()

    assert loaded.default_group_name == "inbox"


def test_normalize_edit_body_cursor_mode_invalid_defaults_to_remember() -> None:
    """Invalid edit cursor mode should fallback to remember."""
    assert normalize_edit_body_cursor_mode("remmeber") == (
        EditBodyCursorMode.REMEMBER
    )


def test_normalize_new_idea_group_mode_invalid_defaults_to_contextual() -> None:
    """Invalid new-idea group mode should fallback to contextual."""
    assert normalize_new_idea_group_mode("legacy") == (
        NewIdeaGroupMode.CONTEXTUAL
    )


def test_normalize_default_group_name_empty_defaults_to_default() -> None:
    """Empty default group config should fallback safely."""
    assert normalize_default_group_name("   ") == "default"


def test_normalize_default_group_name_normalizes_case_and_whitespace() -> None:
    """Configured default group name should normalize consistently."""
    assert normalize_default_group_name("  Inbox  ") == "inbox"

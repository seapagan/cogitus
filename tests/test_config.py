"""Tests for application settings configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.config import (
    DEFAULT_API_AUTH_JWT_ALGORITHM,
    DEFAULT_API_AUTH_TOKEN_EXPIRE_MINUTES,
    AppSettings,
    EditBodyCursorMode,
    NewIdeaGroupMode,
    get_settings,
    normalize_api_auth_jwt_algorithm,
    normalize_api_auth_token_expire_minutes,
    normalize_api_auth_username,
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


def test_settings_persist_api_auth_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings should persist and reload API auth fields."""
    monkeypatch.setattr(
        "simple_toml_settings.settings.xdg_config_home",
        lambda: tmp_path,
    )
    AppSettings._instances.clear()

    settings = get_settings()
    stored_digest = "stored-digest"
    signing_key = "jwt-signing-key"
    settings.api_auth_username = "api-user"
    settings.api_auth_password_hash = stored_digest
    settings.api_auth_jwt_secret = signing_key
    settings.api_auth_jwt_algorithm = "HS512"
    settings.api_auth_token_expire_minutes = 45
    settings.save()

    AppSettings._instances.clear()
    loaded = get_settings()

    assert loaded.api_auth_username == "api-user"
    assert loaded.api_auth_password_hash == stored_digest
    assert loaded.api_auth_jwt_secret == signing_key
    assert loaded.api_auth_jwt_algorithm == "HS512"
    assert loaded.api_auth_token_expire_minutes == 45


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


def test_normalize_api_auth_username_trims_whitespace() -> None:
    """Configured API username should be trimmed."""
    assert normalize_api_auth_username("  api-user  ") == "api-user"


def test_normalize_api_auth_jwt_algorithm_empty_defaults_to_hs256() -> None:
    """Empty JWT algorithm should fallback safely."""
    assert normalize_api_auth_jwt_algorithm("   ") == (
        DEFAULT_API_AUTH_JWT_ALGORITHM
    )


def test_normalize_api_auth_token_expire_minutes_invalid_defaults() -> None:
    """Non-positive token lifetimes should fallback safely."""
    assert normalize_api_auth_token_expire_minutes(0) == (
        DEFAULT_API_AUTH_TOKEN_EXPIRE_MINUTES
    )

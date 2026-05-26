"""Tests for application settings configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.config import (
    DEFAULT_API_AUTH_JWT_ALGORITHM,
    DEFAULT_API_AUTH_TOKEN_EXPIRE_MINUTES,
    DEFAULT_MCP_AUTH_TOKEN_EXPIRE_DAYS,
    AppSettings,
    DataBackendMode,
    EditBodyCursorMode,
    MCPAuthSettings,
    NewIdeaGroupMode,
    get_configured_mcp_auth_settings,
    get_mcp_auth_settings,
    get_settings,
    normalize_api_auth_jwt_algorithm,
    normalize_api_auth_token_expire_minutes,
    normalize_api_auth_username,
    normalize_data_backend_mode,
    normalize_default_group_name,
    normalize_edit_body_cursor_mode,
    normalize_mcp_auth_token_expire_days,
    normalize_new_idea_group_mode,
    normalize_remote_api_base_url,
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


def test_app_settings_save_does_not_serialize_mcp_auth_secret(
    tmp_path: Path,
) -> None:
    """Normal settings saves should not write the MCP auth secret."""
    settings = AppSettings("cogitus", settings_path=tmp_path)
    settings.set("mcp_auth_jwt_secret", "m" * 32, autosave=False)

    settings.save()

    config_text = (tmp_path / "config.toml").read_text(encoding="utf-8")

    assert "mcp_auth_jwt_secret" not in config_text


def test_mcp_auth_settings_persist_jwt_secret(
    tmp_path: Path,
) -> None:
    """MCP auth settings should persist the JWT secret separately."""
    settings = MCPAuthSettings(
        "cogitus_mcp_auth",
        settings_file_name="mcp-auth.toml",
        settings_path=tmp_path,
    )
    settings.jwt_secret = "m" * 32
    settings.save()

    loaded = MCPAuthSettings(
        "cogitus_mcp_auth",
        settings_file_name="mcp-auth.toml",
        settings_path=tmp_path,
    )

    assert loaded.jwt_secret == "m" * 32


def test_get_configured_mcp_auth_settings_migrates_legacy_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy config secrets should be copied to the MCP auth file."""
    monkeypatch.setattr(
        "simple_toml_settings.settings.xdg_config_home",
        lambda: tmp_path,
    )
    AppSettings._instances.clear()
    legacy_secret = "l" * 32
    config_dir = tmp_path / "cogitus"
    config_dir.mkdir()
    config_path = config_dir / "config.toml"
    config_path.write_text(
        '[cogitus]\nschema_version = "none"\n'
        f'mcp_auth_jwt_secret = "{legacy_secret}"\n',
        encoding="utf-8",
    )
    app_settings = get_settings()

    auth_settings = get_configured_mcp_auth_settings(app_settings)
    app_settings.save()

    AppSettings._instances.clear()
    loaded_auth = get_mcp_auth_settings()
    saved_config = config_path.read_text(encoding="utf-8")

    assert auth_settings.jwt_secret == legacy_secret
    assert loaded_auth.jwt_secret == legacy_secret
    assert "mcp_auth_jwt_secret" not in saved_config


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


def test_settings_persist_mcp_auth_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings should persist and reload non-secret MCP auth fields."""
    monkeypatch.setattr(
        "simple_toml_settings.settings.xdg_config_home",
        lambda: tmp_path,
    )
    AppSettings._instances.clear()

    settings = get_settings()
    settings.mcp_auth_token_expire_days = 90
    settings.save()

    AppSettings._instances.clear()
    loaded = get_settings()

    assert loaded.mcp_auth_token_expire_days == 90


def test_settings_persist_remote_backend_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings should persist and reload remote-backend fields."""
    monkeypatch.setattr(
        "simple_toml_settings.settings.xdg_config_home",
        lambda: tmp_path,
    )
    AppSettings._instances.clear()

    settings = get_settings()
    remote_value = "secret" + "-pass"
    settings.data_backend_mode = DataBackendMode.API.value
    settings.remote_api_base_url = "http://127.0.0.1:8000"
    settings.remote_api_username = "api-user"
    settings.remote_api_password = remote_value
    settings.save()

    AppSettings._instances.clear()
    loaded = get_settings()

    assert loaded.data_backend_mode == DataBackendMode.API.value
    assert loaded.remote_api_base_url == "http://127.0.0.1:8000"
    assert loaded.remote_api_username == "api-user"
    assert loaded.remote_api_password == remote_value


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


def test_normalize_data_backend_mode_invalid_defaults_to_local() -> None:
    """Invalid backend modes should fallback to local."""
    assert normalize_data_backend_mode("broken") == DataBackendMode.LOCAL


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


def test_normalize_api_auth_jwt_algorithm_accepts_supported_values() -> None:
    """Configured JWT algorithms should be trimmed and kept."""
    assert normalize_api_auth_jwt_algorithm("  HS512  ") == "HS512"


def test_normalize_api_auth_jwt_algorithm_accepts_eddsa_case() -> None:
    """Mixed-case EdDSA should be preserved by config normalization."""
    assert normalize_api_auth_jwt_algorithm("  EdDSA  ") == "EdDSA"


def test_normalize_api_auth_jwt_algorithm_preserves_noncanonical_case() -> None:
    """Config normalization should preserve trimmed non-canonical values."""
    assert normalize_api_auth_jwt_algorithm("  eddsa  ") == "eddsa"


def test_normalize_api_auth_jwt_algorithm_preserves_unknown_values() -> None:
    """Config normalization should preserve trimmed unknown values."""
    assert normalize_api_auth_jwt_algorithm("HS2256") == "HS2256"


def test_normalize_api_auth_token_expire_minutes_invalid_defaults() -> None:
    """Non-positive token lifetimes should fallback safely."""
    assert normalize_api_auth_token_expire_minutes(0) == (
        DEFAULT_API_AUTH_TOKEN_EXPIRE_MINUTES
    )


def test_normalize_mcp_auth_token_expire_days_invalid_defaults() -> None:
    """Non-positive MCP token lifetimes should fallback safely."""
    assert normalize_mcp_auth_token_expire_days(0) == (
        DEFAULT_MCP_AUTH_TOKEN_EXPIRE_DAYS
    )


def test_normalize_remote_api_base_url_trims_and_drops_trailing_slash() -> None:
    """Configured remote API URLs should normalize consistently."""
    assert (
        normalize_remote_api_base_url("  http://127.0.0.1:8000/  ")
        == "http://127.0.0.1:8000"
    )

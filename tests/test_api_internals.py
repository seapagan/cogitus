"""Focused tests for API internals and lifecycle branches."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pwdlib.exceptions import UnknownHashError

import cogitus.api as api_package
from cogitus.api.dependencies import get_service
from cogitus.api.main import COGITUS_API_DB_PATH_ENV, create_api_app
from cogitus.api.managers.auth_manager import AuthManager
from cogitus.config import DEFAULT_API_AUTH_JWT_ALGORITHM, AppSettings

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import Request
    from pytest_mock import MockerFixture


def test_get_service_raises_when_uninitialized() -> None:
    """Dependency helper should fail clearly without app state service."""
    request = cast(
        "Request",
        SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
    )

    with pytest.raises(TypeError, match="API service is not initialized"):
        get_service(request)


def test_api_package_lazily_exposes_app_factory() -> None:
    """API package should resolve the app factory only on attribute access."""
    assert api_package.create_api_app is create_api_app


def test_api_package_rejects_unknown_attribute() -> None:
    """API package should raise for unknown attributes."""
    missing_attribute = "missing"

    with pytest.raises(AttributeError, match=missing_attribute):
        getattr(api_package, missing_attribute)


def test_create_api_app_uses_default_settings_group(
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
) -> None:
    """App factory should use configured default group with default DB path."""
    fake_db = mocker.Mock()
    get_db = mocker.patch("cogitus.api.main.get_db", return_value=fake_db)
    mocker.patch(
        "cogitus.api.main.get_settings",
        return_value=SimpleNamespace(default_group_name="inbox"),
    )
    monkeypatch.delenv(COGITUS_API_DB_PATH_ENV, raising=False)

    with TestClient(create_api_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    get_db.assert_called_once_with(default_group_name="inbox")
    fake_db.close.assert_called_once_with()


def test_create_api_app_uses_env_db_path(
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """App factory should honor the configured environment DB path."""
    fake_db = mocker.Mock()
    get_db = mocker.patch("cogitus.api.main.get_db", return_value=fake_db)
    mocker.patch(
        "cogitus.api.main.get_settings",
        return_value=SimpleNamespace(default_group_name="default"),
    )
    db_path = tmp_path / "cogitus-api.sqlite"
    monkeypatch.setenv(COGITUS_API_DB_PATH_ENV, str(db_path))

    with TestClient(create_api_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    get_db.assert_called_once_with(
        db_path=str(db_path),
        default_group_name="default",
    )
    fake_db.close.assert_called_once_with()


def test_token_endpoint_returns_service_unavailable_when_auth_unconfigured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Token endpoint should fail clearly when API auth is not configured."""
    monkeypatch.setattr(
        "simple_toml_settings.settings.xdg_config_home",
        lambda: tmp_path,
    )
    AppSettings._instances.clear()

    try:
        with TestClient(
            create_api_app(memory=True, default_group_name="default")
        ) as client:
            response = client.post(
                "/api/v1/auth/token",
                data={"username": "api-user", "password": "secret"},
            )

        assert response.status_code == 503
        assert (
            response.json()["detail"] == "API authentication is not configured"
        )
    finally:
        AppSettings._instances.clear()


def test_auth_manager_rejects_wrong_username(
    configured_api_settings: AppSettings,
    api_auth_credentials: dict[str, str],
) -> None:
    """Auth manager should reject the wrong username."""
    manager = AuthManager(configured_api_settings)

    authenticated = manager.authenticate_user(
        "someone-else",
        api_auth_credentials["password"],
    )

    assert authenticated is None


def test_auth_manager_rejects_wrong_username_with_malformed_dummy_hash(
    configured_api_settings: AppSettings,
    api_auth_credentials: dict[str, str],
    mocker: MockerFixture,
) -> None:
    """Auth manager should fail closed if dummy verification breaks."""
    manager = AuthManager(configured_api_settings)
    mocker.patch(
        "cogitus.api.managers.auth_manager.verify_password",
        side_effect=UnknownHashError("unknown hash"),
    )

    authenticated = manager.authenticate_user(
        "someone-else",
        api_auth_credentials["password"],
    )

    assert authenticated is None


def test_auth_manager_rejects_malformed_password_hash(
    configured_api_settings: AppSettings,
    api_auth_credentials: dict[str, str],
) -> None:
    """Auth manager should fail closed on malformed password hashes."""
    configured_api_settings.api_auth_password_hash = "not" + "-a-valid-hash"
    manager = AuthManager(configured_api_settings)

    authenticated = manager.authenticate_user(
        api_auth_credentials["username"],
        api_auth_credentials["password"],
    )

    assert authenticated is None


def test_auth_manager_defaults_canonical_eddsa_algorithm_to_hs256(
    configured_api_settings: AppSettings,
) -> None:
    """Auth manager should reject non-HMAC JWT algorithms."""
    configured_api_settings.api_auth_jwt_algorithm = "EdDSA"
    manager = AuthManager(configured_api_settings)

    assert manager.jwt_algorithm == DEFAULT_API_AUTH_JWT_ALGORITHM


def test_auth_manager_defaults_invalid_jwt_algorithm_to_hs256(
    configured_api_settings: AppSettings,
) -> None:
    """Auth manager should fall back when configured alg is invalid."""
    configured_api_settings.api_auth_jwt_algorithm = "eddsa"
    manager = AuthManager(configured_api_settings)

    assert manager.jwt_algorithm == DEFAULT_API_AUTH_JWT_ALGORITHM


def test_auth_manager_tokens_always_use_configured_subject(
    configured_api_settings: AppSettings,
) -> None:
    """Auth manager should issue tokens for the configured username."""
    manager = AuthManager(configured_api_settings)
    token = manager.create_access_token()
    decoded = manager.decode_access_token(token)

    assert decoded.username == configured_api_settings.api_auth_username


def test_auth_manager_rejects_token_for_different_subject(
    configured_api_settings: AppSettings,
) -> None:
    """Auth manager should reject a signed token for a different username."""
    manager = AuthManager(configured_api_settings)
    token = jwt.encode(
        {
            "sub": "someone-else",
            "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=5),
        },
        manager.jwt_secret,
        algorithm=manager.jwt_algorithm,
    )

    with pytest.raises(
        HTTPException,
        match="Could not validate credentials",
    ) as exc:
        manager.decode_access_token(token)

    assert exc.value.status_code == 401


def test_auth_manager_honors_zero_token_lifetime(
    configured_api_settings: AppSettings,
) -> None:
    """Auth manager should keep a caller-provided zero token lifetime."""
    manager = AuthManager(configured_api_settings)
    issued_at = datetime.now(tz=timezone.utc)

    token = manager.create_access_token(
        expires_delta=timedelta(0),
    )
    payload = jwt.decode(
        token,
        manager.jwt_secret,
        algorithms=[manager.jwt_algorithm],
        options={"verify_exp": False},
    )
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    assert expires_at <= issued_at + timedelta(seconds=1)

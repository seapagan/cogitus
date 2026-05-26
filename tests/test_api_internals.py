"""Focused tests for API internals and lifecycle branches."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from pwdlib.exceptions import UnknownHashError
from starlette.routing import Mount, Route, WebSocketRoute

import cogitus.api as api_package
from cogitus.api.dependencies import get_current_mcp_user, get_service
from cogitus.api.main import COGITUS_API_DB_PATH_ENV, create_api_app
from cogitus.api.managers.auth_manager import AuthManager, MCPAuthManager
from cogitus.api.mcp import create_mcp_app
from cogitus.api.resources.groups import GROUP_NAMES_RESPONSE_EXAMPLE
from cogitus.api.resources.ideas import (
    IDEA_REFS_RESPONSE_EXAMPLE,
    IDEA_RESPONSE_EXAMPLE,
)
from cogitus.api.resources.tags import TAG_NAMES_RESPONSE_EXAMPLE
from cogitus.config import (
    DEFAULT_API_AUTH_JWT_ALGORITHM,
    AppSettings,
    MCPAuthSettings,
    get_mcp_auth_settings,
    get_settings,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from fastapi import Request
    from pytest_mock import MockerFixture


@pytest.fixture
def isolated_app_settings() -> Generator[None]:
    """Clear singleton app settings before and after isolated tests."""
    AppSettings._instances.clear()
    try:
        yield
    finally:
        AppSettings._instances.clear()


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


def _configured_mcp_auth_settings(secret: str = "m" * 32) -> MCPAuthSettings:
    """Persist isolated MCP auth settings for tests."""
    auth_settings = get_mcp_auth_settings()
    auth_settings.jwt_secret = secret
    auth_settings.save()
    return auth_settings


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


def test_create_api_app_does_not_mount_mcp(
    configured_api_settings: AppSettings,
) -> None:
    """Normal API app should not expose the MCP endpoint."""
    with TestClient(
        create_api_app(memory=True, default_group_name="default")
    ) as client:
        response = client.get("/mcp")

    assert response.status_code == 404


def test_create_mcp_app_exposes_only_mcp_routes(
    configured_api_settings: AppSettings,
) -> None:
    """MCP app should mount MCP without exposing REST routes."""
    _configured_mcp_auth_settings()
    app = create_mcp_app(memory=True, default_group_name="default")

    paths = {
        route.path
        for route in app.routes
        if isinstance(route, Route | Mount | WebSocketRoute)
    }

    assert paths == {"/mcp"}
    assert "/api/v1/ideas" not in paths
    assert "/api/v1/auth/token" not in paths

    with TestClient(app) as client:
        assert client.get("/api").status_code == 404
        assert client.get("/api/v1").status_code == 404
        assert client.get("/api/v1/ideas").status_code == 404
        assert client.post("/api/v1/auth/token").status_code == 404


@pytest.mark.asyncio
async def test_create_mcp_app_lifespan_starts_internal_api(
    configured_api_settings: AppSettings,
) -> None:
    """MCP app lifespan should initialize internal API state for tools."""
    auth_settings = _configured_mcp_auth_settings()
    manager = MCPAuthManager(configured_api_settings, auth_settings)
    token = manager.create_access_token()
    app = create_mcp_app(memory=True, default_group_name="default")

    async with app.router.lifespan_context(app):
        response = await app.state.mcp_api_client.get(
            "/api/v1/ideas/refs",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json() == []


def test_mcp_tool_routes_include_openapi_examples() -> None:
    """MCP-exposed routes should publish realistic OpenAPI examples."""
    openapi = create_api_app(
        memory=True,
        default_group_name="default",
    ).openapi()

    expected_examples = {
        "/api/v1/ideas/refs": IDEA_REFS_RESPONSE_EXAMPLE,
        "/api/v1/ideas/{idea_pk}": IDEA_RESPONSE_EXAMPLE,
        "/api/v1/groups/names": GROUP_NAMES_RESPONSE_EXAMPLE,
        "/api/v1/tags/names": TAG_NAMES_RESPONSE_EXAMPLE,
    }

    for path, expected_example in expected_examples.items():
        response_content = openapi["paths"][path]["get"]["responses"]["200"][
            "content"
        ]

        assert response_content["application/json"]["example"] == (
            expected_example
        )


def test_token_endpoint_returns_service_unavailable_when_auth_unconfigured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_app_settings: None,
) -> None:
    """Token endpoint should fail clearly when API auth is not configured."""
    monkeypatch.setattr(
        "simple_toml_settings.settings.xdg_config_home",
        lambda: tmp_path,
    )
    with TestClient(
        create_api_app(memory=True, default_group_name="default")
    ) as client:
        response = client.post(
            "/api/v1/auth/token",
            data={"username": "api-user", "password": "secret"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "API authentication is not configured"


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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    api_auth_credentials: dict[str, str],
    isolated_app_settings: None,
) -> None:
    """Auth manager should fail closed on malformed password hashes."""
    monkeypatch.setattr(
        "simple_toml_settings.settings.xdg_config_home",
        lambda: tmp_path,
    )
    settings = get_settings()
    settings.api_auth_username = api_auth_credentials["username"]
    settings.api_auth_password_hash = "not" + "-a-valid-hash"
    settings.api_auth_jwt_secret = api_auth_credentials["secret"]
    manager = AuthManager(settings)

    authenticated = manager.authenticate_user(
        api_auth_credentials["username"],
        api_auth_credentials["password"],
    )

    assert authenticated is None


@pytest.mark.parametrize("configured_alg", ["EdDSA", "eddsa"])
def test_auth_manager_defaults_non_hmac_jwt_algorithm_to_hs256(
    configured_api_settings: AppSettings,
    configured_alg: str,
) -> None:
    """Auth manager should fall back for non-HMAC JWT algorithms."""
    configured_api_settings.api_auth_jwt_algorithm = configured_alg
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


def test_mcp_auth_manager_accepts_valid_token(
    configured_api_settings: AppSettings,
) -> None:
    """MCP auth manager should accept its own signed tokens."""
    auth_settings = _configured_mcp_auth_settings()
    manager = MCPAuthManager(configured_api_settings, auth_settings)

    token = manager.create_access_token()
    decoded = manager.decode_access_token(token)

    assert decoded.username == "mcp"


def test_mcp_auth_manager_requires_configured_secret(
    configured_api_settings: AppSettings,
) -> None:
    """MCP auth manager should fail clearly without a signing secret."""
    auth_settings = _configured_mcp_auth_settings("")
    manager = MCPAuthManager(configured_api_settings, auth_settings)

    with pytest.raises(HTTPException) as exc:
        manager.ensure_configured()

    assert exc.value.status_code == 503
    assert exc.value.detail == "MCP authentication is not configured"


def test_mcp_auth_manager_rejects_malformed_token(
    configured_api_settings: AppSettings,
) -> None:
    """MCP auth manager should reject malformed bearer tokens."""
    auth_settings = _configured_mcp_auth_settings()
    manager = MCPAuthManager(configured_api_settings, auth_settings)

    with pytest.raises(HTTPException) as exc:
        manager.decode_access_token("not-a-jwt")

    assert exc.value.status_code == 401


def test_mcp_auth_manager_rejects_wrong_subject_token(
    configured_api_settings: AppSettings,
) -> None:
    """MCP auth manager should reject tokens for non-MCP subjects."""
    auth_settings = _configured_mcp_auth_settings()
    manager = MCPAuthManager(configured_api_settings, auth_settings)
    token = jwt.encode(
        {
            "sub": "api-user",
            "exp": datetime.now(tz=timezone.utc) + timedelta(days=1),
        },
        manager.jwt_secret,
        algorithm=DEFAULT_API_AUTH_JWT_ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc:
        manager.decode_access_token(token)

    assert exc.value.status_code == 401


@pytest.mark.parametrize("credentials", [None, "   "])
def test_get_current_mcp_user_rejects_missing_bearer_credentials(
    configured_api_settings: AppSettings,
    credentials: str | None,
) -> None:
    """MCP auth dependency should reject missing or blank bearer tokens."""
    auth_settings = _configured_mcp_auth_settings()
    manager = MCPAuthManager(configured_api_settings, auth_settings)
    bearer = None
    if credentials is not None:
        bearer = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=credentials,
        )

    with pytest.raises(HTTPException) as exc:
        get_current_mcp_user(bearer, manager)

    assert exc.value.status_code == 401
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}


def test_mcp_auth_manager_rejects_expired_token(
    configured_api_settings: AppSettings,
) -> None:
    """MCP auth manager should reject expired bearer tokens."""
    auth_settings = _configured_mcp_auth_settings()
    manager = MCPAuthManager(configured_api_settings, auth_settings)
    token = manager.create_access_token(expires_delta=timedelta(seconds=-1))

    with pytest.raises(HTTPException) as exc:
        manager.decode_access_token(token)

    assert exc.value.status_code == 401


def test_mcp_auth_manager_rejects_wrong_secret_token(
    configured_api_settings: AppSettings,
) -> None:
    """MCP auth manager should reject tokens signed by another secret."""
    auth_settings = _configured_mcp_auth_settings()
    manager = MCPAuthManager(configured_api_settings, auth_settings)
    token = jwt.encode(
        {
            "sub": "mcp",
            "exp": datetime.now(tz=timezone.utc) + timedelta(days=1),
        },
        "o" * 32,
        algorithm=DEFAULT_API_AUTH_JWT_ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc:
        manager.decode_access_token(token)

    assert exc.value.status_code == 401


def test_auth_manager_honors_zero_token_lifetime(
    configured_api_settings: AppSettings,
) -> None:
    """Auth manager should keep a caller-provided zero token lifetime."""
    manager = AuthManager(configured_api_settings)
    before_issue = datetime.now(tz=timezone.utc)

    token = manager.create_access_token(
        expires_delta=timedelta(0),
    )
    after_issue = datetime.now(tz=timezone.utc)
    payload = jwt.decode(
        token,
        manager.jwt_secret,
        algorithms=[manager.jwt_algorithm],
        options={"verify_exp": False},
    )
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    assert before_issue - timedelta(seconds=1) <= expires_at
    assert expires_at <= after_issue + timedelta(seconds=1)

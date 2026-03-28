"""Focused tests for API internals and lifecycle branches."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
from fastapi.testclient import TestClient

import cogitus.api as api_package
from cogitus.api.dependencies import get_service
from cogitus.api.main import COGITUS_API_DB_PATH_ENV, create_api_app

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

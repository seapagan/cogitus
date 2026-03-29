"""Tests for shared backend datatypes."""

from __future__ import annotations

from cogitus.backends import BackendConfig
from cogitus.config import DataBackendMode


def test_backend_config_repr_redacts_password() -> None:
    """BackendConfig repr should not expose plaintext API passwords."""
    secret_value = "secret" + "-value"
    config = BackendConfig(
        mode=DataBackendMode.API,
        api_base_url="http://remote.test",
        api_username="api-user",
        api_password=secret_value,
    )

    rendered = repr(config)

    assert secret_value not in rendered
    assert "api_password" not in rendered

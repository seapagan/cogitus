"""Authentication manager for the Cogitus API."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from functools import cache
from typing import Final

import jwt
from fastapi import HTTPException, status
from jwt import ExpiredSignatureError, InvalidTokenError
from jwt.algorithms import get_default_algorithms
from pwdlib import PasswordHash

from cogitus.api.models.auth import APIUser, TokenPayload
from cogitus.api.schemas.response.auth import TokenResponse
from cogitus.config import (
    DEFAULT_API_AUTH_JWT_ALGORITHM,
    AppSettings,
    normalize_api_auth_jwt_algorithm,
    normalize_api_auth_token_expire_minutes,
    normalize_api_auth_username,
)

PASSWORD_HASHER: Final = PasswordHash.recommended()
DUMMY_VERIFY_VALUE: Final = (
    "$argon2id$v=19$m=65536,t=3,p=4$wagCPXjifgvUFBzq4hqe3w$"
    "CYaIb8sB+wtD+Vu/P4uod1+Qof8h+1g7bbDlBID48Rc"
)
BEARER_SCHEME: Final = "bearer"
WWW_AUTHENTICATE_HEADER: Final = {"WWW-Authenticate": "Bearer"}


def _invalid_token_header(*, expired: bool = False) -> dict[str, str]:
    """Return a standards-aligned bearer challenge for invalid tokens."""
    if expired:
        return {
            "WWW-Authenticate": (
                'Bearer error="invalid_token", '
                'error_description="The access token expired"'
            )
        }
    return {"WWW-Authenticate": 'Bearer error="invalid_token"'}


@cache
def _valid_jwt_algorithms() -> frozenset[str]:
    """Return canonical JWT algorithm names from PyJWT."""
    return frozenset(
        algorithm
        for algorithm in get_default_algorithms()
        if algorithm.lower() != "none"
    )


def _resolve_jwt_algorithm(algorithm: str) -> str:
    """Validate a configured JWT algorithm against PyJWT names."""
    if algorithm in _valid_jwt_algorithms():
        return algorithm
    return DEFAULT_API_AUTH_JWT_ALGORITHM


def hash_password(password: str) -> str:
    """Hash a plaintext password using the recommended hasher."""
    return PASSWORD_HASHER.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored hash."""
    return PASSWORD_HASHER.verify(plain_password, hashed_password)


class AuthManager:
    """Single-user auth manager backed by persisted config settings."""

    def __init__(self, settings: AppSettings) -> None:
        """Store the config-backed auth settings."""
        self._settings = settings

    @property
    def configured_username(self) -> str:
        """Return the normalized configured API username."""
        return normalize_api_auth_username(self._settings.api_auth_username)

    @property
    def jwt_algorithm(self) -> str:
        """Return the normalized JWT algorithm."""
        return _resolve_jwt_algorithm(
            normalize_api_auth_jwt_algorithm(
                self._settings.api_auth_jwt_algorithm
            )
        )

    @property
    def jwt_secret(self) -> str:
        """Return the configured JWT secret."""
        return self._settings.api_auth_jwt_secret.strip()

    @property
    def token_expire_minutes(self) -> int:
        """Return the normalized token expiry in minutes."""
        return normalize_api_auth_token_expire_minutes(
            self._settings.api_auth_token_expire_minutes
        )

    def is_configured(self) -> bool:
        """Return whether API auth has been configured."""
        return all(
            (
                self.configured_username,
                self._settings.api_auth_password_hash,
                self.jwt_secret,
            )
        )

    def ensure_configured(self) -> None:
        """Raise a clear error when API auth has not been bootstrapped."""
        if not self.is_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="API authentication is not configured",
            )

    def authenticate_user(self, username: str, password: str) -> APIUser | None:
        """Authenticate the configured single API user."""
        self.ensure_configured()

        configured_username = self.configured_username
        if not secrets.compare_digest(username, configured_username):
            verify_password(password, DUMMY_VERIFY_VALUE)
            return None

        if not verify_password(password, self._settings.api_auth_password_hash):
            return None

        return APIUser(username=configured_username)

    def create_access_token(
        self,
        *,
        user: APIUser,
        expires_delta: timedelta | None = None,
    ) -> str:
        """Create a signed JWT access token for the configured user."""
        self.ensure_configured()

        token_lifetime = (
            timedelta(minutes=self.token_expire_minutes)
            if expires_delta is None
            else expires_delta
        )
        payload = {
            "sub": user.username,
            "exp": datetime.now(tz=timezone.utc) + token_lifetime,
        }
        return jwt.encode(
            payload,
            self.jwt_secret,
            algorithm=self.jwt_algorithm,
        )

    def decode_access_token(self, token: str) -> APIUser:
        """Decode and validate a bearer token."""
        self.ensure_configured()

        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers=_invalid_token_header(),
        )

        try:
            payload = TokenPayload.model_validate(
                jwt.decode(
                    token,
                    self.jwt_secret,
                    algorithms=[self.jwt_algorithm],
                )
            )
        except ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers=_invalid_token_header(expired=True),
            ) from exc
        except (InvalidTokenError, ValueError) as exc:
            raise credentials_exception from exc

        if not secrets.compare_digest(payload.sub, self.configured_username):
            raise credentials_exception

        return APIUser(username=payload.sub)

    def create_token_response(
        self,
        *,
        username: str,
        password: str,
    ) -> TokenResponse:
        """Authenticate credentials and return a bearer token response."""
        user = self.authenticate_user(username, password)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers=WWW_AUTHENTICATE_HEADER,
            )

        return TokenResponse(
            access_token=self.create_access_token(user=user),
            token_type=BEARER_SCHEME,
        )

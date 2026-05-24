"""FastAPI dependency helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
    OAuth2PasswordBearer,
)

from cogitus.api.managers.auth_manager import AuthManager, MCPAuthManager
from cogitus.api.managers.group_manager import GroupManager
from cogitus.api.managers.idea_manager import IdeaManager
from cogitus.api.managers.snapshot_manager import SnapshotManager
from cogitus.api.managers.tag_manager import TagManager
from cogitus.config import get_settings
from cogitus.services.idea_service import IdeaService

if TYPE_CHECKING:
    from cogitus.api.models.auth import APIUser

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
mcp_bearer_scheme = HTTPBearer(auto_error=False)


def get_service(request: Request) -> IdeaService:
    """Return the startup-owned idea service from app state."""
    service = getattr(request.app.state, "idea_service", None)
    if not isinstance(service, IdeaService):
        msg = "API service is not initialized"
        raise TypeError(msg)
    return service


def get_idea_manager(
    service: Annotated[IdeaService, Depends(get_service)],
) -> IdeaManager:
    """Return an idea manager bound to the current service."""
    return IdeaManager(service)


def get_group_manager(
    service: Annotated[IdeaService, Depends(get_service)],
) -> GroupManager:
    """Return a group manager bound to the current service."""
    return GroupManager(service)


def get_tag_manager(
    service: Annotated[IdeaService, Depends(get_service)],
) -> TagManager:
    """Return a tag manager bound to the current service."""
    return TagManager(service)


def get_snapshot_manager(
    service: Annotated[IdeaService, Depends(get_service)],
) -> SnapshotManager:
    """Return a snapshot manager bound to the current service."""
    return SnapshotManager(service)


def get_auth_manager() -> AuthManager:
    """Return an auth manager bound to the persisted settings."""
    return AuthManager(get_settings())


def get_mcp_auth_manager() -> MCPAuthManager:
    """Return an MCP auth manager bound to the persisted settings."""
    return MCPAuthManager(get_settings())


def get_current_api_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> APIUser:
    """Return the authenticated API user from the bearer token."""
    return manager.decode_access_token(token)


def get_current_mcp_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(mcp_bearer_scheme),
    ],
    manager: Annotated[MCPAuthManager, Depends(get_mcp_auth_manager)],
) -> APIUser:
    """Return the authenticated MCP user from the bearer token."""
    if credentials is None or not credentials.credentials.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return manager.decode_access_token(credentials.credentials)

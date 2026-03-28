"""FastAPI dependency helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

from cogitus.api.managers.auth_manager import AuthManager
from cogitus.api.managers.group_manager import GroupManager
from cogitus.api.managers.idea_manager import IdeaManager
from cogitus.api.managers.tag_manager import TagManager
from cogitus.config import get_settings
from cogitus.services.idea_service import IdeaService

if TYPE_CHECKING:
    from cogitus.api.models.auth import APIUser

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


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


def get_auth_manager() -> AuthManager:
    """Return an auth manager bound to the persisted settings."""
    return AuthManager(get_settings())


def get_current_api_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> APIUser:
    """Return the authenticated API user from the bearer token."""
    return manager.decode_access_token(token)

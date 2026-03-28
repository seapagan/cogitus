"""FastAPI dependency helpers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from cogitus.api.managers.group_manager import GroupManager
from cogitus.api.managers.idea_manager import IdeaManager
from cogitus.api.managers.tag_manager import TagManager
from cogitus.services.idea_service import IdeaService


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

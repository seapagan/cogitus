"""FastAPI routes for groups."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from cogitus.api.dependencies import get_current_api_user, get_group_manager
from cogitus.api.managers.group_manager import GroupManager
from cogitus.api.schemas.request.group import (
    GroupCreateRequest,
    GroupUpdateRequest,
)
from cogitus.api.schemas.response.group import GroupResponse

router = APIRouter(
    prefix="/api/v1/groups",
    tags=["groups"],
    dependencies=[Depends(get_current_api_user)],
)


@router.get("")
async def list_groups(
    manager: Annotated[GroupManager, Depends(get_group_manager)],
) -> list[GroupResponse]:
    """Return all groups."""
    return manager.list_groups()


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
async def create_group(
    payload: GroupCreateRequest,
    manager: Annotated[GroupManager, Depends(get_group_manager)],
) -> GroupResponse:
    """Create a new group."""
    return manager.create_group(payload)


@router.get("/{group_pk}")
async def get_group(
    group_pk: int,
    manager: Annotated[GroupManager, Depends(get_group_manager)],
) -> GroupResponse:
    """Return a single group."""
    return manager.get_group(group_pk)


@router.put("/{group_pk}")
async def update_group(
    group_pk: int,
    payload: GroupUpdateRequest,
    manager: Annotated[GroupManager, Depends(get_group_manager)],
) -> GroupResponse:
    """Rename an existing group."""
    return manager.update_group(group_pk, payload)


@router.delete("/{group_pk}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_pk: int,
    manager: Annotated[GroupManager, Depends(get_group_manager)],
    move_to_group_pk: Annotated[int | None, Query(ge=1)] = None,
) -> None:
    """Delete an existing group."""
    manager.delete_group(group_pk, move_to_group_pk=move_to_group_pk)

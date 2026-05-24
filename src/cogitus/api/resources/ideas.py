"""FastAPI routes for ideas."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from cogitus.api.dependencies import get_current_api_user, get_idea_manager
from cogitus.api.managers.idea_manager import IdeaManager
from cogitus.api.schemas.request.idea import (
    IdeaCreateRequest,
    IdeaDeleteRequest,
    IdeaUpdateRequest,
)
from cogitus.api.schemas.response.idea import IdeaHashResponse, IdeaResponse

router = APIRouter(
    prefix="/api/v1/ideas",
    tags=["ideas"],
    dependencies=[Depends(get_current_api_user)],
)


@router.get("", operation_id="get_ideas_list")
async def list_ideas(
    manager: Annotated[IdeaManager, Depends(get_idea_manager)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    query: str | None = None,
) -> list[IdeaResponse]:
    """Return ideas with optional search filtering."""
    return manager.list_ideas(limit=limit, offset=offset, query=query)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
async def create_idea(
    payload: IdeaCreateRequest,
    manager: Annotated[IdeaManager, Depends(get_idea_manager)],
) -> IdeaResponse:
    """Create a new idea."""
    return manager.create_idea(payload)


@router.get("/{idea_pk}/hash")
async def get_idea_hash(
    idea_pk: int,
    manager: Annotated[IdeaManager, Depends(get_idea_manager)],
) -> IdeaHashResponse:
    """Return a single idea rendered-detail hash."""
    return manager.get_idea_hash(idea_pk)


@router.get("/{idea_pk}", operation_id="get_single_idea")
async def get_idea(
    idea_pk: int,
    manager: Annotated[IdeaManager, Depends(get_idea_manager)],
) -> IdeaResponse:
    """Return a single idea."""
    return manager.get_idea(idea_pk)


@router.put("/{idea_pk}")
async def update_idea(
    idea_pk: int,
    payload: IdeaUpdateRequest,
    manager: Annotated[IdeaManager, Depends(get_idea_manager)],
) -> IdeaResponse:
    """Update an existing idea."""
    return manager.update_idea(idea_pk, payload)


@router.delete("/{idea_pk}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_idea(
    idea_pk: int,
    payload: IdeaDeleteRequest,
    manager: Annotated[IdeaManager, Depends(get_idea_manager)],
) -> None:
    """Delete an existing idea."""
    manager.delete_idea(
        idea_pk,
        last_known_updated_at=payload.last_known_updated_at,
    )

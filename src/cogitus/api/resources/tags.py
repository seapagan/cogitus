"""FastAPI routes for tags."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from cogitus.api.dependencies import get_current_api_user, get_tag_manager
from cogitus.api.managers.tag_manager import TagManager
from cogitus.api.schemas.request.tag import TagCreateRequest, TagUpdateRequest
from cogitus.api.schemas.response.tag import TagResponse

router = APIRouter(
    prefix="/api/v1/tags",
    tags=["tags"],
    dependencies=[Depends(get_current_api_user)],
)


@router.get("")
async def list_tags(
    manager: Annotated[TagManager, Depends(get_tag_manager)],
) -> list[TagResponse]:
    """Return all tags."""
    return manager.list_tags()


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
async def create_tag(
    payload: TagCreateRequest,
    manager: Annotated[TagManager, Depends(get_tag_manager)],
) -> TagResponse:
    """Create a new tag."""
    return manager.create_tag(payload)


@router.get("/{tag_pk}")
async def get_tag(
    tag_pk: int,
    manager: Annotated[TagManager, Depends(get_tag_manager)],
) -> TagResponse:
    """Return a single tag."""
    return manager.get_tag(tag_pk)


@router.put("/{tag_pk}")
async def update_tag(
    tag_pk: int,
    payload: TagUpdateRequest,
    manager: Annotated[TagManager, Depends(get_tag_manager)],
) -> TagResponse:
    """Rename an existing tag."""
    return manager.update_tag(tag_pk, payload)


@router.delete("/{tag_pk}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_pk: int,
    manager: Annotated[TagManager, Depends(get_tag_manager)],
) -> None:
    """Delete an existing tag."""
    manager.delete_tag(tag_pk)

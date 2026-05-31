"""FastAPI routes for tags."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from cogitus.api.dependencies import get_current_api_user, get_tag_manager
from cogitus.api.managers.tag_manager import TagManager
from cogitus.api.openapi_examples import (
    TAG_NAMES_RESPONSE_EXAMPLE,
    TAG_RESPONSE_EXAMPLE,
    TAGS_RESPONSE_EXAMPLE,
    json_response_example,
)
from cogitus.api.schemas.request.tag import TagCreateRequest, TagUpdateRequest
from cogitus.api.schemas.response.tag import TagResponse

router = APIRouter(
    prefix="/api/v1/tags",
    tags=["tags"],
    dependencies=[Depends(get_current_api_user)],
)


@router.get(
    "",
    responses={
        status.HTTP_200_OK: json_response_example(TAGS_RESPONSE_EXAMPLE),
    },
)
async def list_tags(
    manager: Annotated[TagManager, Depends(get_tag_manager)],
) -> list[TagResponse]:
    """Return all tags."""
    return manager.list_tags()


@router.get(
    "/names",
    operation_id="get_tag_names",
    response_description="Tag names available for tag:<name> filters.",
    summary="List Cogitus tag names",
    responses={
        status.HTTP_200_OK: json_response_example(TAG_NAMES_RESPONSE_EXAMPLE),
    },
)
async def list_tag_names(
    manager: Annotated[TagManager, Depends(get_tag_manager)],
) -> list[str]:
    """Return a list of all tag names."""
    return manager.list_tag_names()


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: json_response_example(TAG_RESPONSE_EXAMPLE),
    },
)
async def create_tag(
    payload: TagCreateRequest,
    manager: Annotated[TagManager, Depends(get_tag_manager)],
) -> TagResponse:
    """Create a new tag."""
    return manager.create_tag(payload)


@router.get(
    "/{tag_pk}",
    responses={
        status.HTTP_200_OK: json_response_example(TAG_RESPONSE_EXAMPLE),
    },
)
async def get_tag(
    tag_pk: int,
    manager: Annotated[TagManager, Depends(get_tag_manager)],
) -> TagResponse:
    """Return a single tag."""
    return manager.get_tag(tag_pk)


@router.put(
    "/{tag_pk}",
    responses={
        status.HTTP_200_OK: json_response_example(TAG_RESPONSE_EXAMPLE),
    },
)
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

"""FastAPI routes for ideas."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from cogitus.api.dependencies import get_current_api_user, get_idea_manager
from cogitus.api.managers.idea_manager import IdeaManager
from cogitus.api.openapi_examples import (
    IDEA_HASH_RESPONSE_EXAMPLE,
    IDEA_REFS_RESPONSE_EXAMPLE,
    IDEA_RESPONSE_EXAMPLE,
    IDEAS_RESPONSE_EXAMPLE,
    json_response_example,
)
from cogitus.api.schemas.request.idea import (
    IdeaCreateRequest,
    IdeaDeleteRequest,
    IdeaUpdateRequest,
)
from cogitus.api.schemas.response.idea import (
    IdeaHashResponse,
    IdeaRefResponse,
    IdeaResponse,
)

router = APIRouter(
    prefix="/api/v1/ideas",
    tags=["ideas"],
    dependencies=[Depends(get_current_api_user)],
)


@router.get(
    "",
    operation_id="get_ideas_list",
    response_description="Ideas matching the list or search request.",
    summary="Search or list Cogitus ideas",
    responses={
        status.HTTP_200_OK: json_response_example(IDEAS_RESPONSE_EXAMPLE),
    },
)
async def list_ideas(
    manager: Annotated[IdeaManager, Depends(get_idea_manager)],
    limit: Annotated[
        int,
        Query(
            description="Maximum number of ideas to return.",
            ge=1,
            le=1000,
        ),
    ] = 100,
    offset: Annotated[
        int,
        Query(description="Number of matching ideas to skip.", ge=0),
    ] = 0,
    query: Annotated[
        str | None,
        Query(
            description=(
                "Optional free-text search. Supports tag:<name> and "
                "group:<name> subtree filters, with and/or between filters."
            ),
        ),
    ] = None,
) -> list[IdeaResponse]:
    """Return ideas, most recently updated first.

    When `query` is provided, search visible idea text and optional structured
    filters. Use `tag:<name>` to filter by tag, or `group:<name>` to filter by
    a group and its child groups, and combine filters with `and` or `or`.
    """
    return manager.list_ideas(limit=limit, offset=offset, query=query)


@router.get(
    "/refs",
    operation_id="get_idea_refs",
    response_description="Lightweight idea references matching the request.",
    summary="Search or list Cogitus idea references",
    responses={
        status.HTTP_200_OK: json_response_example(IDEA_REFS_RESPONSE_EXAMPLE),
    },
)
async def list_idea_refs(
    manager: Annotated[IdeaManager, Depends(get_idea_manager)],
    limit: Annotated[
        int,
        Query(
            description="Maximum number of idea references to return.",
            ge=1,
            le=1000,
        ),
    ] = 100,
    offset: Annotated[
        int,
        Query(description="Number of matching idea references to skip.", ge=0),
    ] = 0,
    query: Annotated[
        str | None,
        Query(
            description=(
                "Optional free-text search. Supports tag:<name> and "
                "group:<name> subtree filters, with and/or between filters."
            ),
        ),
    ] = None,
) -> list[IdeaRefResponse]:
    """Return lightweight idea references, most recently updated first.

    Use this to find candidate ideas by `pk` and `title`, then call
    `get_single_idea` with the selected `pk` to inspect the full idea.
    """
    return manager.list_idea_refs(limit=limit, offset=offset, query=query)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: json_response_example(IDEA_RESPONSE_EXAMPLE),
    },
)
async def create_idea(
    payload: IdeaCreateRequest,
    manager: Annotated[IdeaManager, Depends(get_idea_manager)],
) -> IdeaResponse:
    """Create a new idea."""
    return manager.create_idea(payload)


@router.get(
    "/{idea_pk}/hash",
    responses={
        status.HTTP_200_OK: json_response_example(IDEA_HASH_RESPONSE_EXAMPLE),
    },
)
async def get_idea_hash(
    idea_pk: int,
    manager: Annotated[IdeaManager, Depends(get_idea_manager)],
) -> IdeaHashResponse:
    """Return a single idea rendered-detail hash."""
    return manager.get_idea_hash(idea_pk)


@router.get(
    "/{idea_pk}",
    operation_id="get_single_idea",
    response_description="The requested idea with its group and tags.",
    summary="Get a Cogitus idea by primary key",
    responses={
        status.HTTP_200_OK: json_response_example(IDEA_RESPONSE_EXAMPLE),
    },
)
async def get_idea(
    idea_pk: Annotated[
        int,
        Path(
            description=(
                "Cogitus idea primary key, usually from get_ideas_list results."
            ),
        ),
    ],
    manager: Annotated[IdeaManager, Depends(get_idea_manager)],
) -> IdeaResponse:
    """Return one idea by primary key.

    Use this after list or search results when the full idea body, group, and
    tags are needed for a specific idea.
    """
    return manager.get_idea(idea_pk)


@router.put(
    "/{idea_pk}",
    responses={
        status.HTTP_200_OK: json_response_example(IDEA_RESPONSE_EXAMPLE),
    },
)
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

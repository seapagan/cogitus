"""FastAPI routes for groups."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, status

from cogitus.api.dependencies import get_current_api_user, get_group_manager
from cogitus.api.managers.group_manager import GroupManager
from cogitus.api.openapi_examples import (
    API_AUTH_ERROR_RESPONSE,
    API_AUTH_NOT_CONFIGURED_RESPONSE,
    GROUP_CONFLICT_RESPONSE,
    GROUP_CREATE_REQUEST_OPENAPI_EXAMPLES,
    GROUP_CREATE_VALIDATION_ERROR_RESPONSE,
    GROUP_DELETE_CONFLICT_RESPONSE,
    GROUP_DELETE_NOT_FOUND_RESPONSE,
    GROUP_DELETE_QUERY_VALIDATION_ERROR_RESPONSE,
    GROUP_NAMES_RESPONSE_EXAMPLE,
    GROUP_NOT_FOUND_RESPONSE,
    GROUP_PARENT_NOT_FOUND_RESPONSE,
    GROUP_PATH_VALIDATION_ERROR_RESPONSE,
    GROUP_RESPONSE_OPENAPI_EXAMPLES,
    GROUP_UPDATE_CONFLICT_RESPONSE,
    GROUP_UPDATE_REQUEST_OPENAPI_EXAMPLES,
    GROUP_UPDATE_VALIDATION_ERROR_RESPONSE,
    GROUPS_RESPONSE_EXAMPLE,
    json_response_example,
    json_response_examples,
)
from cogitus.api.schemas.request.group import (
    GroupCreateRequest,
    GroupUpdateRequest,
)
from cogitus.api.schemas.response.group import GroupResponse

router = APIRouter(
    prefix="/api/v1/groups",
    tags=["groups"],
    dependencies=[Depends(get_current_api_user)],
    responses={
        status.HTTP_401_UNAUTHORIZED: API_AUTH_ERROR_RESPONSE,
        status.HTTP_503_SERVICE_UNAVAILABLE: API_AUTH_NOT_CONFIGURED_RESPONSE,
    },
)


@router.get(
    "",
    responses={
        status.HTTP_200_OK: json_response_example(GROUPS_RESPONSE_EXAMPLE),
    },
)
async def list_groups(
    manager: Annotated[GroupManager, Depends(get_group_manager)],
) -> list[GroupResponse]:
    """Return all groups."""
    return manager.list_groups()


@router.get(
    "/names",
    operation_id="get_group_names",
    response_description="Group names available for group:<name> filters.",
    summary="List Cogitus group names",
    responses={
        status.HTTP_200_OK: json_response_example(GROUP_NAMES_RESPONSE_EXAMPLE),
    },
)
async def list_group_names(
    manager: Annotated[GroupManager, Depends(get_group_manager)],
) -> list[str]:
    """Return a list of all group names."""
    return manager.list_group_names()


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: json_response_examples(
            GROUP_RESPONSE_OPENAPI_EXAMPLES,
        ),
        status.HTTP_404_NOT_FOUND: GROUP_PARENT_NOT_FOUND_RESPONSE,
        status.HTTP_409_CONFLICT: GROUP_CONFLICT_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: (
            GROUP_CREATE_VALIDATION_ERROR_RESPONSE
        ),
    },
)
async def create_group(
    payload: Annotated[
        GroupCreateRequest,
        Body(openapi_examples=GROUP_CREATE_REQUEST_OPENAPI_EXAMPLES),
    ],
    manager: Annotated[GroupManager, Depends(get_group_manager)],
) -> GroupResponse:
    """Create a new group."""
    return manager.create_group(payload)


@router.get(
    "/{group_pk}",
    responses={
        status.HTTP_200_OK: json_response_examples(
            GROUP_RESPONSE_OPENAPI_EXAMPLES,
        ),
        status.HTTP_404_NOT_FOUND: GROUP_NOT_FOUND_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: (
            GROUP_PATH_VALIDATION_ERROR_RESPONSE
        ),
    },
)
async def get_group(
    group_pk: int,
    manager: Annotated[GroupManager, Depends(get_group_manager)],
) -> GroupResponse:
    """Return a single group."""
    return manager.get_group(group_pk)


@router.put(
    "/{group_pk}",
    responses={
        status.HTTP_200_OK: json_response_examples(
            GROUP_RESPONSE_OPENAPI_EXAMPLES,
        ),
        status.HTTP_404_NOT_FOUND: GROUP_NOT_FOUND_RESPONSE,
        status.HTTP_409_CONFLICT: GROUP_UPDATE_CONFLICT_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: (
            GROUP_UPDATE_VALIDATION_ERROR_RESPONSE
        ),
    },
)
async def update_group(
    group_pk: int,
    payload: Annotated[
        GroupUpdateRequest,
        Body(openapi_examples=GROUP_UPDATE_REQUEST_OPENAPI_EXAMPLES),
    ],
    manager: Annotated[GroupManager, Depends(get_group_manager)],
) -> GroupResponse:
    """Rename an existing group."""
    return manager.update_group(group_pk, payload)


@router.delete(
    "/{group_pk}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_404_NOT_FOUND: GROUP_DELETE_NOT_FOUND_RESPONSE,
        status.HTTP_409_CONFLICT: GROUP_DELETE_CONFLICT_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: (
            GROUP_DELETE_QUERY_VALIDATION_ERROR_RESPONSE
        ),
    },
)
async def delete_group(
    group_pk: int,
    manager: Annotated[GroupManager, Depends(get_group_manager)],
    move_to_group_pk: Annotated[int | None, Query(ge=1)] = None,
) -> None:
    """Delete an existing group."""
    manager.delete_group(group_pk, move_to_group_pk=move_to_group_pk)

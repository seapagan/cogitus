"""FastAPI route for full dataset snapshots."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from cogitus.api.dependencies import (
    get_current_api_user,
    get_snapshot_manager,
)
from cogitus.api.managers.snapshot_manager import SnapshotManager
from cogitus.api.openapi_examples import (
    API_AUTH_ERROR_RESPONSE,
    API_AUTH_NOT_CONFIGURED_RESPONSE,
    SNAPSHOT_RESPONSE_EXAMPLE,
    SNAPSHOT_STATE_RESPONSE_EXAMPLE,
    json_response_example,
)
from cogitus.api.schemas.response.snapshot import (
    SnapshotResponse,
    SnapshotStateResponse,
)

router = APIRouter(
    prefix="/api/v1/snapshot",
    tags=["snapshot"],
    dependencies=[Depends(get_current_api_user)],
    responses={
        status.HTTP_401_UNAUTHORIZED: API_AUTH_ERROR_RESPONSE,
        status.HTTP_503_SERVICE_UNAVAILABLE: API_AUTH_NOT_CONFIGURED_RESPONSE,
    },
)


@router.get(
    "",
    responses={
        status.HTTP_200_OK: json_response_example(SNAPSHOT_RESPONSE_EXAMPLE),
    },
)
async def get_snapshot(
    manager: Annotated[SnapshotManager, Depends(get_snapshot_manager)],
) -> SnapshotResponse:
    """Return one consistent full snapshot for remote cache refresh."""
    return manager.get_snapshot()


@router.get(
    "/state",
    responses={
        status.HTTP_200_OK: json_response_example(
            SNAPSHOT_STATE_RESPONSE_EXAMPLE,
        ),
    },
)
async def get_snapshot_state(
    manager: Annotated[SnapshotManager, Depends(get_snapshot_manager)],
) -> SnapshotStateResponse:
    """Return the current remote dataset hash."""
    return manager.get_state()

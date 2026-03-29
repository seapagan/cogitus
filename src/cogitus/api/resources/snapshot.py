"""FastAPI route for full dataset snapshots."""

from typing import Annotated

from fastapi import APIRouter, Depends

from cogitus.api.dependencies import (
    get_current_api_user,
    get_snapshot_manager,
)
from cogitus.api.managers.snapshot_manager import SnapshotManager
from cogitus.api.schemas.response.snapshot import SnapshotResponse

router = APIRouter(
    prefix="/api/v1/snapshot",
    tags=["snapshot"],
    dependencies=[Depends(get_current_api_user)],
)


@router.get("")
async def get_snapshot(
    manager: Annotated[SnapshotManager, Depends(get_snapshot_manager)],
) -> SnapshotResponse:
    """Return one consistent full snapshot for remote cache refresh."""
    return manager.get_snapshot()

"""API manager for full dataset snapshots."""

from cogitus.api.mappers import (
    to_group_response,
    to_idea_response,
    to_tag_response,
)
from cogitus.api.schemas.response.snapshot import (
    SnapshotResponse,
    SnapshotStateResponse,
)
from cogitus.services.idea_service import IdeaService


class SnapshotManager:
    """API-facing orchestration for one consistent dataset snapshot."""

    def __init__(self, service: IdeaService) -> None:
        """Initialize with a service instance."""
        self._service = service

    def get_snapshot(self) -> SnapshotResponse:
        """Return groups, tags, and ideas from one DB transaction."""
        with self._service.transaction():
            return SnapshotResponse(
                groups=[
                    to_group_response(group)
                    for group in self._service.list_groups()
                ],
                tags=[
                    to_tag_response(tag) for tag in self._service.list_tags()
                ],
                ideas=[
                    to_idea_response(idea)
                    for idea in self._service.list_snapshot_ideas()
                ],
            )

    def get_state(self) -> SnapshotStateResponse:
        """Return the current dataset state hash."""
        return SnapshotStateResponse(
            dataset_hash=self._service.get_dataset_hash()
        )

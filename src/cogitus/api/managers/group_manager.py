"""API manager for groups."""

from cogitus.api.managers.common import (
    raise_http_for_value_error,
    raise_not_found,
)
from cogitus.api.mappers import to_group_response
from cogitus.api.schemas.request.group import (
    GroupCreateRequest,
    GroupUpdateRequest,
)
from cogitus.api.schemas.response.group import GroupResponse
from cogitus.services.idea_service import IdeaService


class GroupManager:
    """API-facing orchestration for group resources."""

    def __init__(self, service: IdeaService) -> None:
        """Initialize with a service instance."""
        self._service = service

    def list_groups(self) -> list[GroupResponse]:
        """Return all groups."""
        return [
            to_group_response(group) for group in self._service.list_groups()
        ]

    def list_group_names(self) -> list[str]:
        """Return all group names."""
        return [group.name for group in self.list_groups()]

    def get_group(self, group_pk: int) -> GroupResponse:
        """Return a single group response."""
        group = self._service.get_group(group_pk)
        if group is None:
            raise_not_found("Group", group_pk)
        return to_group_response(group)

    def create_group(self, payload: GroupCreateRequest) -> GroupResponse:
        """Create a new group."""
        try:
            group = self._service.create_group(payload.name)
        except ValueError as error:
            raise_http_for_value_error(error)
        return to_group_response(group)

    def update_group(
        self,
        group_pk: int,
        payload: GroupUpdateRequest,
    ) -> GroupResponse:
        """Update an existing group."""
        try:
            group = self._service.rename_group(group_pk, payload.name)
        except ValueError as error:
            raise_http_for_value_error(error)
        if group is None:
            raise_not_found("Group", group_pk)
        return to_group_response(group)

    def delete_group(
        self,
        group_pk: int,
        *,
        move_to_group_pk: int | None = None,
    ) -> None:
        """Delete an existing group."""
        if self._service.get_group(group_pk) is None:
            raise_not_found("Group", group_pk)
        try:
            self._service.delete_group(
                group_pk,
                move_to_group_pk=move_to_group_pk,
            )
        except ValueError as error:
            raise_http_for_value_error(error)

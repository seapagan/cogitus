"""API manager for tags."""

from cogitus.api.managers.common import (
    raise_http_for_value_error,
    raise_not_found,
)
from cogitus.api.mappers import to_tag_response
from cogitus.api.schemas.request.tag import TagCreateRequest, TagUpdateRequest
from cogitus.api.schemas.response.tag import TagResponse
from cogitus.services.idea_service import IdeaService


class TagManager:
    """API-facing orchestration for tag resources."""

    def __init__(self, service: IdeaService) -> None:
        """Initialize with a service instance."""
        self._service = service

    def list_tags(self) -> list[TagResponse]:
        """Return all tags."""
        return [to_tag_response(tag) for tag in self._service.list_tags()]

    def get_tag(self, tag_pk: int) -> TagResponse:
        """Return a single tag response."""
        tag = self._service.get_tag(tag_pk)
        if tag is None:
            raise_not_found("Tag", tag_pk)
        return to_tag_response(tag)

    def create_tag(self, payload: TagCreateRequest) -> TagResponse:
        """Create a new tag."""
        try:
            tag = self._service.create_tag(payload.name)
        except ValueError as error:
            raise_http_for_value_error(error)
        return to_tag_response(tag)

    def update_tag(
        self,
        tag_pk: int,
        payload: TagUpdateRequest,
    ) -> TagResponse:
        """Rename an existing tag."""
        try:
            tag = self._service.rename_tag(tag_pk, payload.name)
        except ValueError as error:
            raise_http_for_value_error(error)
        if tag is None:
            raise_not_found("Tag", tag_pk)
        return to_tag_response(tag)

    def delete_tag(self, tag_pk: int) -> None:
        """Delete an existing tag."""
        if self._service.get_tag(tag_pk) is None:
            raise_not_found("Tag", tag_pk)
        self._service.delete_tag(tag_pk)

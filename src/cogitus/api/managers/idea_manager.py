"""API manager for ideas."""

from cogitus.api.managers.common import (
    raise_http_for_value_error,
    raise_not_found,
)
from cogitus.api.mappers import to_idea_response
from cogitus.api.schemas.request.idea import (
    IdeaCreateRequest,
    IdeaUpdateRequest,
)
from cogitus.api.schemas.response.idea import (
    IdeaHashResponse,
    IdeaRefResponse,
    IdeaResponse,
)
from cogitus.services.idea_service import IdeaService


class IdeaManager:
    """API-facing orchestration for idea resources."""

    def __init__(self, service: IdeaService) -> None:
        """Initialize with a service instance."""
        self._service = service

    def list_ideas(
        self,
        *,
        limit: int,
        offset: int,
        query: str | None = None,
    ) -> list[IdeaResponse]:
        """Return ideas for the list endpoint."""
        if query:
            ideas = self._service.search_ideas(query)
            ideas = ideas[offset : offset + limit]
        else:
            ideas = self._service.list_ideas(limit=limit, offset=offset)
        return [to_idea_response(idea) for idea in ideas]

    def list_idea_refs(
        self,
        *,
        limit: int,
        offset: int,
        query: str | None = None,
    ) -> list[IdeaRefResponse]:
        """Return lightweight idea references for browsing/search."""
        ideas = self.list_ideas(limit=limit, offset=offset, query=query)
        return [
            IdeaRefResponse(
                pk=idea.pk,
                title=idea.title,
                group=idea.group.name,
                tags=[tag.name for tag in idea.tags],
                updated_at=idea.updated_at,
            )
            for idea in ideas
        ]

    def get_idea(self, idea_pk: int) -> IdeaResponse:
        """Return a single idea response."""
        idea = self._service.get_idea_with_relations(idea_pk)
        if idea is None:
            raise_not_found("Idea", idea_pk)
        return to_idea_response(idea)

    def get_idea_hash(self, idea_pk: int) -> IdeaHashResponse:
        """Return the rendered-detail hash for one idea."""
        detail_hash = self._service.get_idea_detail_hash(idea_pk)
        if detail_hash is None:
            raise_not_found("Idea", idea_pk)
        return IdeaHashResponse(pk=idea_pk, detail_hash=detail_hash)

    def create_idea(self, payload: IdeaCreateRequest) -> IdeaResponse:
        """Create a new idea."""
        try:
            created = self._service.create_idea(
                title=payload.title,
                body=payload.body,
                tags=payload.tags,
                group_pk=payload.group_pk,
            )
        except ValueError as error:
            raise_http_for_value_error(error)

        return self.get_idea(created.pk)

    def update_idea(
        self,
        idea_pk: int,
        payload: IdeaUpdateRequest,
    ) -> IdeaResponse:
        """Update an existing idea."""
        try:
            updated = self._service.update_idea(
                idea_pk,
                title=payload.title,
                body=payload.body,
                tags=payload.tags,
                group_pk=payload.group_pk,
                last_known_updated_at=payload.last_known_updated_at,
            )
        except ValueError as error:
            raise_http_for_value_error(error)

        if updated is None:
            raise_not_found("Idea", idea_pk)
        return self.get_idea(updated.pk)

    def delete_idea(
        self,
        idea_pk: int,
        *,
        last_known_updated_at: int | None = None,
    ) -> None:
        """Delete an existing idea."""
        if self._service.get_idea(idea_pk) is None:
            raise_not_found("Idea", idea_pk)
        try:
            self._service.delete_idea(
                idea_pk,
                last_known_updated_at=last_known_updated_at,
            )
        except ValueError as error:
            raise_http_for_value_error(error)

"""Map Cogitus domain models to API response schemas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.api.schemas.response.group import GroupResponse
from cogitus.api.schemas.response.idea import IdeaResponse
from cogitus.api.schemas.response.tag import TagResponse

if TYPE_CHECKING:
    from cogitus.models.group import Group
    from cogitus.models.idea import Idea
    from cogitus.models.tag import Tag


def to_group_response(group: Group) -> GroupResponse:
    """Return the API response schema for a group."""
    return GroupResponse(
        pk=group.pk,
        created_at=group.created_at,
        updated_at=group.updated_at,
        name=group.name,
    )


def to_tag_response(tag: Tag) -> TagResponse:
    """Return the API response schema for a tag."""
    return TagResponse(
        pk=tag.pk,
        created_at=tag.created_at,
        updated_at=tag.updated_at,
        name=tag.name,
    )


def to_idea_response(idea: Idea) -> IdeaResponse:
    """Return the API response schema for an idea."""
    return IdeaResponse(
        pk=idea.pk,
        created_at=idea.created_at,
        updated_at=idea.updated_at,
        title=idea.title,
        body=idea.body,
        group=to_group_response(idea.group),
        tags=[to_tag_response(tag) for tag in idea.tags.fetch_all()],
    )

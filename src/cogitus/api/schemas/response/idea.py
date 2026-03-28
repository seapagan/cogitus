"""Response schemas for ideas."""

from pydantic import BaseModel, ConfigDict

from cogitus.api.schemas.response.group import GroupResponse
from cogitus.api.schemas.response.tag import TagResponse


class IdeaResponse(BaseModel):
    """API response for an idea."""

    model_config = ConfigDict(extra="forbid")

    pk: int
    created_at: int
    updated_at: int
    title: str
    body: str
    group: GroupResponse
    tags: list[TagResponse]

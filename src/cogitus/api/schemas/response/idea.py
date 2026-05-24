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
    detail_hash: str
    group: GroupResponse
    tags: list[TagResponse]


class IdeaHashResponse(BaseModel):
    """API response for one idea rendered-detail hash."""

    model_config = ConfigDict(extra="forbid")

    pk: int
    detail_hash: str


class IdeaRefResponse(BaseModel):
    """Lightweight API response for choosing an idea to inspect."""

    model_config = ConfigDict(extra="forbid")

    pk: int
    title: str
    group: str
    tags: list[str]
    updated_at: int

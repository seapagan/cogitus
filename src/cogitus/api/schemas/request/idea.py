"""Request schemas for ideas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class IdeaCreateRequest(BaseModel):
    """Payload for creating an idea."""

    model_config = ConfigDict(extra="forbid")

    title: str
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    group_pk: int | None = None


class IdeaUpdateRequest(BaseModel):
    """Payload for replacing an idea."""

    model_config = ConfigDict(extra="forbid")

    title: str
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    group_pk: int | None = None
    last_known_updated_at: int | None = None

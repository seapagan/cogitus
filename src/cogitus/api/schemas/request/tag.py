"""Request schemas for tags."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TagCreateRequest(BaseModel):
    """Payload for creating a tag."""

    model_config = ConfigDict(extra="forbid")

    name: str


class TagUpdateRequest(BaseModel):
    """Payload for renaming a tag."""

    model_config = ConfigDict(extra="forbid")

    name: str

"""Request schemas for groups."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class GroupCreateRequest(BaseModel):
    """Payload for creating a group."""

    model_config = ConfigDict(extra="forbid")

    name: str


class GroupUpdateRequest(BaseModel):
    """Payload for renaming a group."""

    model_config = ConfigDict(extra="forbid")

    name: str

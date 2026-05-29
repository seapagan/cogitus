"""Response schemas for groups."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class GroupResponse(BaseModel):
    """API response for a group."""

    model_config = ConfigDict(extra="forbid")

    pk: int
    created_at: int
    updated_at: int
    name: str
    parent_pk: int | None = None

"""Response schemas for tags."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TagResponse(BaseModel):
    """API response for a tag."""

    model_config = ConfigDict(extra="forbid")

    pk: int
    created_at: int
    updated_at: int
    name: str

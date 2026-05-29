"""Request schemas for groups."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GroupCreateRequest(BaseModel):
    """Payload for creating a group."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    name: str = Field(min_length=1)
    parent_pk: int | None = Field(default=None, ge=1)


class GroupUpdateRequest(BaseModel):
    """Payload for renaming a group."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    name: str = Field(min_length=1)

"""Response schemas for full remote snapshots."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from cogitus.api.schemas.response.group import GroupResponse
    from cogitus.api.schemas.response.idea import IdeaResponse
    from cogitus.api.schemas.response.tag import TagResponse


class SnapshotResponse(BaseModel):
    """API response for one consistent remote dataset snapshot."""

    model_config = ConfigDict(extra="forbid")

    groups: list[GroupResponse]
    tags: list[TagResponse]
    ideas: list[IdeaResponse]

"""Shared backend datatypes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cogitus.api.schemas.response.group import GroupResponse
    from cogitus.api.schemas.response.idea import IdeaResponse
    from cogitus.api.schemas.response.tag import TagResponse
    from cogitus.config import DataBackendMode


@dataclass(frozen=True)
class BackendConfig:
    """Persisted backend configuration used by the app."""

    mode: DataBackendMode
    api_base_url: str
    api_username: str
    api_password: str


@dataclass(frozen=True)
class RemoteSnapshot:
    """Full remote dataset used to refresh the local cache."""

    groups: list[GroupResponse]
    tags: list[TagResponse]
    ideas: list[IdeaResponse]

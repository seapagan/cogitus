"""Search result contracts for ranked idea retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cogitus.models.idea import Idea


@dataclass(frozen=True)
class SearchResult:
    """Ranked search result with optional snippet metadata."""

    idea: Idea
    score: float
    snippet: str | None = None

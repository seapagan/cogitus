"""Search result contracts for ranked idea retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from cogitus.models.idea import Idea


SearchMatchSource = Literal["title", "body", "tag", "group"]


@dataclass(frozen=True)
class SearchMatchFragment:
    """One visible search match fragment for a result idea."""

    source: SearchMatchSource
    text: str
    rank: int
    is_synthetic: bool = False


@dataclass(frozen=True)
class SearchResult:
    """Ranked search result with optional fragment metadata."""

    idea: Idea
    score: float
    matches: tuple[SearchMatchFragment, ...] = ()
    snippet: str | None = None

    def __post_init__(self) -> None:
        """Provide backward-compatible snippet-only construction."""
        if self.matches or self.snippet is None:
            return
        object.__setattr__(
            self,
            "matches",
            (
                SearchMatchFragment(
                    source="body",
                    text=self.snippet,
                    rank=0,
                ),
            ),
        )

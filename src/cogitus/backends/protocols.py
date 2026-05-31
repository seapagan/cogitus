"""Protocols describing the app-facing backend surface."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from cogitus.backends.types import RemoteSyncResult
    from cogitus.models.group import Group
    from cogitus.models.idea import Idea
    from cogitus.models.tag import Tag
    from cogitus.search import SearchResult


@runtime_checkable
class IdeaBackend(Protocol):
    """Behavior the TUI requires from a data backend."""

    @property
    def default_group_name(self) -> str:
        """Return the canonical fallback group name."""

    def create_idea(
        self,
        title: str,
        body: str = "",
        tags: list[str] | None = None,
        group_pk: int | None = None,
    ) -> Idea:
        """Create a new idea."""

    def update_idea(
        self,
        pk: int,
        title: str,
        body: str,
        tags: list[str] | None = None,
        group_pk: int | None = None,
    ) -> Idea | None:
        """Update an existing idea."""

    def rename_idea(self, pk: int, title: str) -> Idea | None:
        """Rename an idea."""

    def delete_idea(self, pk: int) -> None:
        """Delete an idea."""

    def get_idea(self, pk: int) -> Idea | None:
        """Fetch a single idea."""

    def list_tags_in_use(self) -> list[Tag]:
        """List tags linked to at least one idea."""

    def list_tags_with_usage(self) -> list[tuple[Tag, int]]:
        """List tags with usage counts."""

    def get_idea_cursor_position(self, idea_pk: int) -> int | None:
        """Return the remembered cursor position for an idea."""

    def set_idea_cursor_position(self, idea_pk: int, position: int) -> None:
        """Persist the remembered cursor position for an idea."""

    def get_idea_scroll_position(
        self,
        idea_pk: int,
        detail_hash: str,
    ) -> int | None:
        """Return the remembered rendered-pane scroll position."""

    def set_idea_scroll_position(
        self,
        idea_pk: int,
        detail_hash: str,
        scroll_y: int,
    ) -> None:
        """Persist the remembered rendered-pane scroll position."""

    def list_groups(self) -> list[Group]:
        """List all groups."""

    def get_group(self, pk: int) -> Group | None:
        """Fetch a single group."""

    def create_group(
        self,
        name: str,
        parent_pk: int | None = None,
    ) -> Group:
        """Create a group."""

    def rename_group(self, pk: int, name: str) -> Group | None:
        """Rename a group."""

    def has_ideas_in_group(self, group_pk: int) -> bool:
        """Return whether the group contains ideas."""

    def list_ideas_grouped(
        self,
        query: str | None = None,
    ) -> list[tuple[Group, list[Idea]]]:
        """List grouped ideas for the left panel."""

    def search_results(self, query: str) -> list[SearchResult]:
        """Return grouped search results."""

    def delete_group(
        self,
        group_pk: int,
        move_to_group_pk: int | None = None,
    ) -> None:
        """Delete a group, optionally moving ideas elsewhere."""


@runtime_checkable
class SyncingIdeaBackend(IdeaBackend, Protocol):
    """Optional extension for backends that can pull remote state."""

    def sync_from_remote(self) -> RemoteSyncResult:
        """Refresh the local cache from the remote API."""

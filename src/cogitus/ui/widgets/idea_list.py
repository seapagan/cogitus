"""Left pane: scrollable idea list with search."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Input, ListItem, ListView, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.timer import Timer

    from cogitus.models.idea import Idea

_DAYS_IN_WEEK = 7


def _format_timestamp(unix_ts: int) -> str:
    """Format a unix timestamp as a relative string."""
    if unix_ts == 0:
        return ""
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    delta = now - dt
    if delta.days == 0:
        hours = delta.seconds // 3600
        if hours == 0:
            minutes = delta.seconds // 60
            return "just now" if minutes == 0 else f"{minutes}m ago"
        return f"{hours}h ago"
    if delta.days == 1:
        return "yesterday"
    if delta.days < _DAYS_IN_WEEK:
        return f"{delta.days}d ago"
    return dt.strftime("%Y-%m-%d")


class IdeaListItem(Static):
    """A single idea row in the list."""

    def __init__(self, idea: Idea) -> None:
        """Initialize with an idea.

        Args:
            idea: The Idea to display.
        """
        self.idea = idea
        super().__init__()

    def compose(self) -> ComposeResult:
        """Compose the idea item display."""
        tags = self.idea.tags.fetch_all()
        tag_str = " ".join(f"[{t.name}]" for t in tags)
        timestamp = _format_timestamp(self.idea.updated_at)
        yield Static(self.idea.title, classes="idea-title")
        meta_parts = []
        if tag_str:
            meta_parts.append(f"[green]{tag_str}[/green]")
        if timestamp:
            meta_parts.append(f"[dim]{timestamp}[/dim]")
        if meta_parts:
            yield Static(
                "  ".join(meta_parts),
                classes="idea-meta",
                markup=True,
            )


class IdeaListPanel(Vertical):
    """Left panel with search input and idea list."""

    search_query: reactive[str] = reactive("", layout=True)

    class IdeaSelected(Message):
        """Fired when an idea is selected."""

        def __init__(self, idea: Idea) -> None:
            """Initialize with the selected idea.

            Args:
                idea: The selected Idea.
            """
            self.idea = idea
            super().__init__()

    class SearchChanged(Message):
        """Fired when search query changes (debounced)."""

        def __init__(self, query: str) -> None:
            """Initialize with the search query.

            Args:
                query: The search query string.
            """
            self.query = query
            super().__init__()

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
    ) -> None:
        """Initialize the idea list panel.

        Args:
            name: The name of the widget.
            id: The CSS ID of the widget.
            classes: The CSS classes of the widget.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._ideas: list[Idea] = []
        self._debounce_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        """Compose the idea list panel."""
        yield Input(
            placeholder="Search ideas... (/ to focus)",
            id="search-input",
        )
        yield ListView(id="idea-list")

    def load_ideas(self, ideas: list[Idea]) -> None:
        """Replace the displayed ideas."""
        self._ideas = ideas
        list_view = self.query_one("#idea-list", ListView)
        list_view.clear()
        for idea in ideas:
            item = ListItem(IdeaListItem(idea))
            item.idea = idea  # type: ignore[attr-defined]
            list_view.append(item)

    def get_selected_idea(self) -> Idea | None:
        """Return the currently highlighted idea."""
        list_view = self.query_one("#idea-list", ListView)
        if list_view.highlighted_child is not None:
            idea: Idea | None = getattr(
                list_view.highlighted_child, "idea", None
            )
            return idea
        return None

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes with debounce."""
        if event.input.id == "search-input":
            if self._debounce_timer is not None:
                self._debounce_timer.stop()
            self._debounce_timer = self.set_timer(
                0.2,
                lambda: self._fire_search(event.value),
            )

    def _fire_search(self, query: str) -> None:
        """Post the debounced search message."""
        self.post_message(self.SearchChanged(query))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle idea selection from list."""
        idea = getattr(event.item, "idea", None)
        if idea is not None:
            self.post_message(self.IdeaSelected(idea))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle idea highlight change."""
        if event.item is not None:
            idea = getattr(event.item, "idea", None)
            if idea is not None:
                self.post_message(self.IdeaSelected(idea))

    def focus_search(self) -> None:
        """Focus the search input."""
        self.query_one("#search-input", Input).focus()

    def clear_search(self) -> None:
        """Clear the search input."""
        search = self.query_one("#search-input", Input)
        search.value = ""
        search.focus()

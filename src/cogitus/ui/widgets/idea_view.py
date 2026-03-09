"""Right pane: rendered markdown view of an idea."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import cached_property
from typing import TYPE_CHECKING

from textual.containers import Vertical, VerticalScroll
from textual.widgets import Markdown, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from cogitus.models.idea import Idea


def _format_full_timestamp(unix_ts: int) -> str:
    """Format a unix timestamp as a full date-time."""
    if unix_ts == 0:
        return "\u2014"
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


class IdeaView(Vertical):
    """Right panel showing full detail of an idea."""

    can_focus = False

    def compose(self) -> ComposeResult:
        """Compose the idea detail view."""
        yield Vertical(
            Static("", id="idea-view-title"),
            Static("", id="idea-view-tags", markup=True),
            Static("", id="idea-view-timestamps"),
            id="idea-view-header",
        )
        yield VerticalScroll(
            Markdown("", id="idea-view-body"),
            id="idea-view-container",
        )

    @cached_property
    def _content_container(self) -> VerticalScroll:
        """Return the stable scroll container for the idea view."""
        return self.query_one("#idea-view-container", VerticalScroll)

    @cached_property
    def _title_widget(self) -> Static:
        """Return the stable title widget."""
        return self.query_one("#idea-view-title", Static)

    @cached_property
    def _tags_widget(self) -> Static:
        """Return the stable tags widget."""
        return self.query_one("#idea-view-tags", Static)

    @cached_property
    def _timestamps_widget(self) -> Static:
        """Return the stable timestamp widget."""
        return self.query_one("#idea-view-timestamps", Static)

    @cached_property
    def _body_widget(self) -> Markdown:
        """Return the stable markdown body widget."""
        return self.query_one("#idea-view-body", Markdown)

    def focus_content(self) -> None:
        """Focus the scrollable content container for keyboard navigation."""
        self._content_container.focus()

    def show_idea(self, idea: Idea) -> None:
        """Display the given idea in the view."""
        self._title_widget.update(idea.title)

        tags = idea.tags.fetch_all()
        tag_str = " ".join(f"[green]\\[{t.name}][/green]" for t in tags)
        self._tags_widget.update(tag_str)

        created = _format_full_timestamp(idea.created_at)
        updated = _format_full_timestamp(idea.updated_at)
        self._timestamps_widget.update(
            f"Created: {created}  |  Updated: {updated}"
        )

        self._body_widget.update(idea.body or "*No content*")

    def show_empty(self) -> None:
        """Show the empty state."""
        self._title_widget.update("")
        self._tags_widget.update("")
        self._timestamps_widget.update("")
        self._body_widget.update(
            "*Select an idea from the list, or press* `n` *to create one.*"
        )

    def selected_body_text(self) -> str | None:
        """Return the currently selected rendered body text, if any."""
        selection = self._body_widget.text_selection
        if selection is None:
            return None

        selected = self._body_widget.get_selection(selection)
        if selected is None:
            return None
        widget_text, _ = selected
        return widget_text or None

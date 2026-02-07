"""Right pane: rendered markdown view of an idea."""

from __future__ import annotations

from datetime import datetime, timezone
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

    can_focus = True

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

    def show_idea(self, idea: Idea) -> None:
        """Display the given idea in the view."""
        title_w = self.query_one("#idea-view-title", Static)
        tags_w = self.query_one("#idea-view-tags", Static)
        ts_w = self.query_one("#idea-view-timestamps", Static)
        body_w = self.query_one("#idea-view-body", Markdown)

        title_w.update(idea.title)

        tags = idea.tags.fetch_all()
        tag_str = " ".join(f"[green]\\[{t.name}][/green]" for t in tags)
        tags_w.update(tag_str)

        created = _format_full_timestamp(idea.created_at)
        updated = _format_full_timestamp(idea.updated_at)
        ts_w.update(f"Created: {created}  |  Updated: {updated}")

        body_w.update(idea.body or "*No content*")

    def show_empty(self) -> None:
        """Show the empty state."""
        title_w = self.query_one("#idea-view-title", Static)
        tags_w = self.query_one("#idea-view-tags", Static)
        ts_w = self.query_one("#idea-view-timestamps", Static)
        body_w = self.query_one("#idea-view-body", Markdown)

        title_w.update("")
        tags_w.update("")
        ts_w.update("")
        body_w.update(
            "*Select an idea from the list, or press* `n` *to create one.*"
        )

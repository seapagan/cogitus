"""Tests for UI widgets."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input, Markdown, OptionList, Static, Tree

from cogitus.ui.widgets.idea_list import (
    IdeaListPanel,
    IdeaTreeNodeData,
    _format_timestamp,
)
from cogitus.ui.widgets.idea_view import IdeaView, _format_full_timestamp

if TYPE_CHECKING:
    from textual.widget import Widget

    from cogitus.services.idea_service import IdeaService


class _WidgetApp(App[None]):
    """Small app to mount a single widget for tests."""

    def __init__(self, widget: Widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        """Compose with one mounted widget."""
        yield self._widget


def _to_unix(dt: datetime) -> int:
    """Convert datetime to unix seconds."""
    return int(dt.timestamp())


def test_format_timestamp_branches() -> None:
    """Relative timestamp helper should cover all formatting branches."""
    now = datetime.now(tz=timezone.utc)
    assert _format_timestamp(0) == ""
    assert _format_timestamp(_to_unix(now)) == "just now"
    assert _format_timestamp(_to_unix(now - timedelta(minutes=2))) == "2m ago"
    assert _format_timestamp(_to_unix(now - timedelta(hours=2))) == "2h ago"
    assert _format_timestamp(_to_unix(now - timedelta(days=1))) == "yesterday"
    assert _format_timestamp(_to_unix(now - timedelta(days=3))) == "3d ago"

    older = now - timedelta(days=10)
    assert _format_timestamp(_to_unix(older)) == older.strftime("%Y-%m-%d")


def test_format_full_timestamp_branches() -> None:
    """Full timestamp helper should return fallback and formatted values."""
    assert _format_full_timestamp(0) == "—"
    ts = _to_unix(datetime(2025, 2, 7, 14, 5, tzinfo=timezone.utc))
    assert _format_full_timestamp(ts) == "2025-02-07 14:05 UTC"


@pytest.mark.asyncio
async def test_idea_list_panel_load_and_selection(
    service: IdeaService,
) -> None:
    """List panel should load ideas and return highlighted selection."""
    service.create_idea("First")
    second = service.create_idea("Second")
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        grouped = service.list_ideas_grouped()
        panel.load_grouped_ideas(grouped)
        panel.select_idea(second.pk)
        await pilot.pause()

        selected = panel.get_selected_idea()

        assert selected is not None
        assert selected.pk == second.pk


@pytest.mark.asyncio
async def test_idea_list_panel_methods_and_events(
    service: IdeaService,
) -> None:
    """List panel helpers and event handlers should behave correctly."""
    idea = service.create_idea("Event target")
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)
    async with app.run_test() as pilot:
        panel.load_grouped_ideas(service.list_ideas_grouped())
        tree = panel.query_one("#idea-list", Tree)
        panel.select_idea(idea.pk)
        await pilot.pause()

        search = panel.query_one("#search-input", Input)
        search.value = "abc"
        panel.focus_search()
        assert app.focused is search

        panel.clear_search()
        assert search.value == ""
        assert app.focused is search

        panel.on_input_changed(Input.Changed(search, "xyz"))
        await pilot.pause()
        panel._fire_search("needle")
        assert tree.cursor_node is not None
        panel.on_tree_node_selected(Tree.NodeSelected(tree.cursor_node))


@pytest.mark.asyncio
async def test_idea_list_panel_remaining_branches(
    service: IdeaService,
) -> None:
    """Cover load_ideas compatibility and non-idea/group selections."""
    idea = service.create_idea("Compat idea")
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.load_ideas([idea])
        await pilot.pause()

        assert panel.select_idea(999999) is False

        tree = panel.query_one("#idea-list", Tree)
        tree.move_cursor(tree.root, animate=False)
        await pilot.pause()
        assert panel.get_selected_idea() is None
        assert panel.get_selected_group_pk() is None

        # Add malformed idea node to exercise idea_pk is None branch.
        malformed = tree.root.add_leaf("Bad")
        malformed.data = IdeaTreeNodeData(kind="idea", idea_pk=None)
        tree.move_cursor(malformed, animate=False)
        await pilot.pause()
        assert panel.get_selected_idea() is None

        panel.load_grouped_ideas(service.list_ideas_grouped())
        group_node = tree.root.children[0]
        tree.move_cursor(group_node, animate=False)
        await pilot.pause()
        assert panel.get_selected_group_pk() is not None


@pytest.mark.asyncio
async def test_idea_list_panel_search_autocomplete_flow(
    service: IdeaService,
) -> None:
    """Search autocomplete should suggest operators and values."""
    backend = service.create_group("backend")
    service.create_idea("With python", tags=["python"], group_pk=backend.pk)
    service.create_idea("With api", tags=["api"], group_pk=backend.pk)

    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.set_autocomplete_sources(
            tags=[tag.name for tag in service.list_tags()],
            groups=[group.name for group in service.list_groups()],
        )
        search = panel.query_one("#search-input", Input)
        autocomplete = panel.query_one("#search-autocomplete", OptionList)

        search.focus()
        await pilot.pause()

        await pilot.press("t")
        await pilot.pause()
        assert not autocomplete.has_class("-hidden")
        assert [str(option.prompt) for option in autocomplete.options] == [
            "tag:",
        ]

        await pilot.press("enter")
        await pilot.pause()
        assert search.value == "tag:"

        await pilot.press("tab")
        await pilot.pause()
        assert not autocomplete.has_class("-hidden")
        assert [str(option.prompt) for option in autocomplete.options] == [
            "api",
            "python",
        ]

        highlighted = autocomplete.highlighted
        assert highlighted == 0

        await pilot.press("tab")
        await pilot.pause()
        assert autocomplete.highlighted == 1

        await pilot.press("shift+tab")
        await pilot.pause()
        assert autocomplete.highlighted == 0

        await pilot.press("down")
        await pilot.pause()
        assert autocomplete.highlighted == 1

        await pilot.press("up")
        await pilot.pause()
        assert autocomplete.highlighted == 0

        await pilot.press("enter")
        await pilot.pause()
        assert search.value == "tag:api"
        assert autocomplete.has_class("-hidden")


def test_idea_list_panel_get_selected_idea_with_missing_pk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_selected_idea should return None when idea node has no PK."""
    panel = IdeaListPanel(id="idea-list-panel")

    class _Node:
        data = IdeaTreeNodeData(kind="idea", idea_pk=None)

    class _Tree:
        cursor_node = _Node()

    monkeypatch.setattr(panel, "query_one", lambda *_args, **_kwargs: _Tree())
    assert panel.get_selected_idea() is None


@pytest.mark.asyncio
async def test_idea_view_show_and_empty(service: IdeaService) -> None:
    """Idea view should render populated and empty states."""
    idea = service.create_idea(
        "Renderable",
        body="Body text",
        tags=["python", "testing"],
    )
    view = IdeaView(id="content-panel")
    app = _WidgetApp(view)

    async with app.run_test() as pilot:
        view.show_idea(idea)
        await pilot.pause()

        title = view.query_one("#idea-view-title", Static)
        tags = view.query_one("#idea-view-tags", Static)
        timestamps = view.query_one("#idea-view-timestamps", Static)
        body = view.query_one("#idea-view-body", Markdown)

        assert "Renderable" in str(title.content)
        assert "python" in str(tags.content)
        assert "Created:" in str(timestamps.content)
        assert body._markdown is not None

        view.show_empty()
        await pilot.pause()

        assert str(title.content) == ""
        assert str(tags.content) == ""
        assert str(timestamps.content) == ""
        assert "Select an idea from the list" in str(body._markdown)

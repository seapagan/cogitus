"""Tests for UI widgets."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import Input, Markdown, OptionList, Static, Tree
from textual.widgets.option_list import Option

from cogitus import datefmt as datefmt_module
from cogitus.datefmt import (
    DateOrder,
    format_full_timestamp,
    format_relative_timestamp,
)
from cogitus.models.group import Group
from cogitus.search import SearchMatchFragment, SearchResult
from cogitus.ui.widgets.autocomplete import _AutocompleteState
from cogitus.ui.widgets.idea_list import (
    IdeaListPanel,
    IdeaTreeNodeData,
    _resolve_autocomplete_state,
    _token_bounds,
    _truncate_snippet,
)
from cogitus.ui.widgets.idea_view import (
    IdeaView,
    _tag_click_markup,
)
from cogitus.ui.widgets.search_results import (
    SearchResultSelection,
    SearchResultsList,
    _marked_text_to_text,
)
from tests.helpers import DEEP_GROUP_DEPTH, _focused_widget, deep_group_chain

if TYPE_CHECKING:
    from pytest_mock import MockerFixture
    from textual.events import Key
    from textual.widget import Widget
    from textual.widgets.tree import TreeNode

    from cogitus.models.idea import Idea
    from cogitus.services.idea_service import IdeaService


class _WidgetApp(App[None]):
    """Small app to mount a single widget for tests."""

    def __init__(self, widget: Widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        """Compose with one mounted widget."""
        yield self._widget


class _FrozenDateTime:
    """Controllable datetime replacement for relative-time tests."""

    current = datetime.now(tz=timezone.utc)

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> datetime:
        """Return the configured current time."""
        if tz is None:
            return cls.current.replace(tzinfo=None)
        return cls.current.astimezone(tz)

    @classmethod
    def fromtimestamp(
        cls,
        timestamp: float,
        tz: tzinfo | None = None,
    ) -> datetime:
        """Delegate timestamp conversion to the real datetime class."""
        return datetime.fromtimestamp(timestamp, tz=tz)


def _to_unix(dt: datetime) -> int:
    """Convert datetime to unix seconds."""
    return int(dt.timestamp())


def _fake_idea_tree_node(line: int, pk: int) -> TreeNode[IdeaTreeNodeData]:
    """Build a minimal typed stand-in for a tree idea node."""
    return cast(
        "TreeNode[IdeaTreeNodeData]",
        SimpleNamespace(
            line=line,
            data=IdeaTreeNodeData(kind="idea", idea_pk=pk),
        ),
    )


def test_format_timestamp_branches() -> None:
    """Relative timestamp helper should cover all formatting branches."""
    now = datetime.now(tz=timezone.utc)
    assert (
        format_relative_timestamp(0, tz=timezone.utc, date_order=DateOrder.ISO)
        == ""
    )
    assert (
        format_relative_timestamp(
            _to_unix(now), tz=timezone.utc, date_order=DateOrder.ISO
        )
        == "just now"
    )
    assert (
        format_relative_timestamp(
            _to_unix(now - timedelta(minutes=2)),
            tz=timezone.utc,
            date_order=DateOrder.ISO,
        )
        == "2m ago"
    )
    assert (
        format_relative_timestamp(
            _to_unix(now - timedelta(hours=2)),
            tz=timezone.utc,
            date_order=DateOrder.ISO,
        )
        == "2h ago"
    )
    assert (
        format_relative_timestamp(
            _to_unix(now - timedelta(days=1)),
            tz=timezone.utc,
            date_order=DateOrder.ISO,
        )
        == "yesterday"
    )
    assert (
        format_relative_timestamp(
            _to_unix(now - timedelta(days=3)),
            tz=timezone.utc,
            date_order=DateOrder.ISO,
        )
        == "3d ago"
    )

    older = now - timedelta(days=10)
    assert format_relative_timestamp(
        _to_unix(older), tz=timezone.utc, date_order=DateOrder.ISO
    ) == older.strftime("%Y-%m-%d")


def test_format_full_timestamp_branches() -> None:
    """Full timestamp helper should return fallback and formatted values."""
    assert (
        format_full_timestamp(0, tz=timezone.utc, date_order=DateOrder.ISO)
        == "—"
    )
    ts = _to_unix(datetime(2025, 2, 7, 14, 5, tzinfo=timezone.utc))
    assert (
        format_full_timestamp(ts, tz=timezone.utc, date_order=DateOrder.ISO)
        == "2025-02-07 14:05 UTC"
    )


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
async def test_idea_list_panel_can_load_without_auto_selection(
    service: IdeaService,
) -> None:
    """Grouped loads can intentionally leave the tree with no selection."""
    first = service.create_idea("First")
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.load_grouped_ideas(service.list_ideas_grouped())
        assert panel.select_idea(first.pk) is True
        panel.load_grouped_ideas(
            service.list_ideas_grouped(),
            auto_select_first=False,
        )
        await pilot.pause()

        assert panel.get_selected_idea() is None
        assert panel.get_selected_group_pk() is None


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
async def test_idea_list_panel_refreshes_bindings_on_search_and_selection(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Search/selection changes should trigger footer binding refreshes."""
    second = service.create_idea("Beta python")
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test():
        panel.load_grouped_ideas(service.list_ideas_grouped())
        tree = panel.query_one("#idea-list", Tree)
        search = panel.query_one("#search-input", Input)
        refresh = mocker.patch.object(panel.screen, "refresh_bindings")

        panel.select_idea(second.pk)
        assert refresh.call_count >= 1

        refresh.reset_mock()
        search.value = "python"
        panel.on_input_changed(Input.Changed(search, "python"))
        assert refresh.call_count >= 1

        refresh.reset_mock()
        cursor_node = tree.cursor_node
        assert cursor_node is not None
        panel.on_tree_node_highlighted(Tree.NodeHighlighted(cursor_node))
        assert refresh.call_count >= 1

        refresh.reset_mock()
        panel.on_tree_node_selected(Tree.NodeSelected(cursor_node))
        assert refresh.call_count >= 1


@pytest.mark.asyncio
async def test_idea_list_panel_uses_stronger_group_label_emphasis(
    service: IdeaService,
) -> None:
    """Group headings should be stronger than idea titles in the tree."""
    backend = service.create_group("Backend")
    idea = service.create_idea("API polish", group_pk=backend.pk)
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.load_grouped_ideas(service.list_ideas_grouped())
        await pilot.pause()

        tree = panel.query_one("#idea-list", Tree)
        assert tree.show_root is False
        group_node = next(
            node
            for node in tree.root.children
            if node.data == IdeaTreeNodeData(kind="group", group_pk=backend.pk)
        )
        idea_node = group_node.children[0]

        assert isinstance(group_node.label, Text)
        assert group_node.label.plain == f"{backend.name} (1)"
        assert group_node.label.style == "bold"
        assert any(
            span.style == "not bold dim" for span in group_node.label.spans
        )

        assert isinstance(idea_node.label, Text)
        assert idea_node.label.plain.startswith(idea.title)
        assert idea_node.label.style == ""
        assert any(span.style == "dim" for span in idea_node.label.spans)


@pytest.mark.asyncio
async def test_idea_list_panel_renders_nested_groups(
    service: IdeaService,
) -> None:
    """Grouped tree should render child groups under their parents."""
    parent = service.create_group("parent")
    child = service.create_group("child", parent_pk=parent.pk)
    idea = service.create_idea("Nested idea", group_pk=child.pk)
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.load_grouped_ideas(service.list_ideas_grouped())
        await pilot.pause()

        tree = panel.query_one("#idea-list", Tree)
        parent_node = next(
            node
            for node in tree.root.children
            if node.data == IdeaTreeNodeData(kind="group", group_pk=parent.pk)
        )
        child_node = next(
            node
            for node in parent_node.children
            if node.data == IdeaTreeNodeData(kind="group", group_pk=child.pk)
        )

        assert child_node.children[0].data == IdeaTreeNodeData(
            kind="idea",
            group_pk=child.pk,
            idea_pk=idea.pk,
        )


@pytest.mark.asyncio
async def test_idea_list_panel_loads_deep_group_hierarchy() -> None:
    """Grouped tree rendering should not recurse through deep hierarchies."""
    groups = deep_group_chain()
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test():
        panel.load_grouped_ideas([(group, []) for group in groups])

        assert DEEP_GROUP_DEPTH in panel._group_nodes_by_pk


@pytest.mark.asyncio
async def test_idea_list_panel_renders_cyclic_group_component_once() -> None:
    """Corrupt cyclic group components should remain visible once."""
    groups = [
        Group(pk=1, created_at=1, updated_at=1, name="alpha", parent_pk=2),
        Group(pk=2, created_at=2, updated_at=2, name="beta", parent_pk=1),
    ]
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test():
        panel.load_grouped_ideas([(group, []) for group in groups])

        tree = panel.query_one("#idea-list", Tree)
        stack = list(tree.root.children)
        group_pks: list[int] = []
        while stack:
            node = stack.pop()
            if node.data is not None and node.data.kind == "group":
                group_pks.append(node.data.group_pk)
            stack.extend(node.children)

        assert sorted(group_pks) == [1, 2]


@pytest.mark.asyncio
async def test_idea_list_panel_refreshes_relative_timestamps_in_place(
    service: IdeaService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Relative timestamps should update without rebuilding the tree."""
    base_time = datetime(2025, 2, 7, 14, 5, tzinfo=timezone.utc)
    _FrozenDateTime.current = base_time
    monkeypatch.setattr(datefmt_module, "datetime", _FrozenDateTime)

    idea = service.create_idea("Fresh")
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        grouped = service.list_ideas_grouped()
        grouped_idea = next(
            candidate
            for _, ideas in grouped
            for candidate in ideas
            if candidate.pk == idea.pk
        )
        grouped_idea.updated_at = _to_unix(base_time)

        panel.load_grouped_ideas(grouped)
        await pilot.pause()

        node = panel._idea_nodes_by_pk[idea.pk]
        assert isinstance(node.label, Text)
        assert node.label.plain == "Fresh [just now]"

        _FrozenDateTime.current = base_time + timedelta(hours=2)
        panel.refresh_relative_timestamps()
        await pilot.pause()

        assert isinstance(node.label, Text)
        assert node.label.plain == "Fresh [2h ago]"


@pytest.mark.asyncio
async def test_idea_list_panel_relative_timestamp_refresh_keeps_selection(
    service: IdeaService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In-place timestamp refresh should not disturb current selection."""
    base_time = datetime(2025, 2, 7, 14, 5, tzinfo=timezone.utc)
    _FrozenDateTime.current = base_time
    monkeypatch.setattr(datefmt_module, "datetime", _FrozenDateTime)

    first = service.create_idea("First")
    second = service.create_idea("Second")
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        grouped = service.list_ideas_grouped()
        for _, ideas in grouped:
            for candidate in ideas:
                candidate.updated_at = _to_unix(base_time)

        panel.load_grouped_ideas(grouped)
        assert panel.select_idea(second.pk) is True
        await pilot.pause()

        tree = panel.query_one("#idea-list", Tree)
        cursor_before = tree.cursor_node
        selected_before = panel.get_selected_idea()

        _FrozenDateTime.current = base_time + timedelta(hours=1)
        panel.refresh_relative_timestamps()
        await pilot.pause()

        selected_after = panel.get_selected_idea()
        assert selected_before is not None
        assert selected_after is not None
        assert selected_before.pk == second.pk
        assert selected_after.pk == second.pk
        assert tree.cursor_node is cursor_before
        assert first.pk in panel._idea_nodes_by_pk


@pytest.mark.asyncio
async def test_idea_list_panel_relative_timestamp_refresh_skips_search_mode(
    service: IdeaService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Active search should suppress the background timestamp relabel."""
    base_time = datetime(2025, 2, 7, 14, 5, tzinfo=timezone.utc)
    _FrozenDateTime.current = base_time
    monkeypatch.setattr(datefmt_module, "datetime", _FrozenDateTime)

    idea = service.create_idea("Fresh")
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        grouped = service.list_ideas_grouped()
        grouped_idea = next(
            candidate
            for _, ideas in grouped
            for candidate in ideas
            if candidate.pk == idea.pk
        )
        grouped_idea.updated_at = _to_unix(base_time)

        panel.load_grouped_ideas(grouped)
        await pilot.pause()

        node = panel._idea_nodes_by_pk[idea.pk]
        assert isinstance(node.label, Text)
        assert node.label.plain == "Fresh [just now]"

        panel.query_one("#search-input", Input).value = "fresh"
        _FrozenDateTime.current = base_time + timedelta(hours=2)
        panel.refresh_relative_timestamps()
        await pilot.pause()

        assert isinstance(node.label, Text)
        assert node.label.plain == "Fresh [just now]"


@pytest.mark.asyncio
async def test_idea_list_panel_relative_timestamp_refresh_skips_missing_idea(
    service: IdeaService,
) -> None:
    """Missing cached ideas should be ignored during relabel refresh."""
    idea = service.create_idea("Fresh")
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.load_grouped_ideas(service.list_ideas_grouped())
        await pilot.pause()

        node = panel._idea_nodes_by_pk[idea.pk]
        original_label = node.label
        del panel._ideas_by_pk[idea.pk]

        panel.refresh_relative_timestamps()
        await pilot.pause()

        assert node.label == original_label


@pytest.mark.asyncio
async def test_idea_list_panel_renders_search_snippets(
    service: IdeaService,
) -> None:
    """Active search should render dedicated heading + match rows."""
    idea = service.create_idea(
        "Snippet target",
        body="A searchable body snippet for python queries",
    )
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.load_grouped_search_results(
            [
                (
                    idea.group,
                    [
                        SearchResult(
                            idea=idea,
                            score=-1.0,
                            snippet="searchable body snippet for python",
                        )
                    ],
                )
            ],
            show_match_rows=True,
        )
        await pilot.pause()

        results = panel.query_one("#search-results", SearchResultsList)
        prompts = [
            option.prompt.plain
            if hasattr(option.prompt, "plain")
            else str(option.prompt)
            for option in results.options
        ]

        assert any("Snippet target" in prompt for prompt in prompts)
        assert any(
            "searchable body snippet for python" in prompt for prompt in prompts
        )


@pytest.mark.asyncio
async def test_idea_list_panel_search_mode_helpers_cover_selection_paths(
    service: IdeaService,
) -> None:
    """Search-mode helpers should select ideas and hide group selection."""
    idea = service.create_idea("Helper target", body="python helper")
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.query_one("#search-input", Input).value = "python"
        panel.load_search_results(
            service.search_results("python"),
            show_match_rows=True,
        )
        await pilot.pause()

        assert panel.select_idea(idea.pk) is True
        assert panel.get_selected_idea() is not None
        assert panel.get_selected_group_pk() is None
        assert panel.active_results_widget() is panel.query_one(
            "#search-results",
            SearchResultsList,
        )
        assert panel.select_idea(999999) is False


@pytest.mark.asyncio
async def test_idea_list_panel_whitespace_keeps_search_mode_until_clear(
    service: IdeaService,
) -> None:
    """Whitespace-only input should keep search semantics until clear runs."""
    idea = service.create_idea("Whitespace target", body="python helper")
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        search = panel.query_one("#search-input", Input)
        results = panel.query_one("#search-results", SearchResultsList)

        search.value = "python"
        panel.load_search_results(
            service.search_results("python"),
            show_match_rows=True,
        )
        await pilot.pause()

        search.value = "   "
        panel.on_input_changed(Input.Changed(search, "   "))
        await pilot.pause()

        assert panel.current_search_query() == ""
        assert panel.raw_search_query() == "   "
        assert panel.search_is_active() is True
        assert panel.active_results_widget() is results
        selected = panel.get_selected_idea()
        assert selected is not None
        assert selected.pk == idea.pk

        panel.dismiss_autocomplete()
        panel.focus_preferred_list_widget()
        await pilot.pause()
        assert app.focused is results


@pytest.mark.asyncio
async def test_idea_list_panel_structured_only_search_uses_idea_rows(
    service: IdeaService,
) -> None:
    """Structured-only search should render selectable idea rows."""
    tagged = service.create_idea("Tagged idea", tags=["python"])
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.query_one("#search-input", Input).value = "tag:python"
        panel.load_search_results(
            service.search_results("tag:python"),
            show_match_rows=False,
        )
        await pilot.pause()

        results = panel.query_one("#search-results", SearchResultsList)

        assert len(results.options) == 1
        assert results.options[0].id == f"idea-{tagged.pk}"
        selected = panel.get_selected_idea()
        assert selected is not None
        assert selected.pk == tagged.pk


@pytest.mark.asyncio
async def test_idea_list_panel_tag_only_text_match_returns_no_results(
    service: IdeaService,
) -> None:
    """Tag-only free-text matches should not render any result rows."""
    service.create_idea("No visible text hit", tags=["python"])
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.query_one("#search-input", Input).value = "python"
        panel.load_search_results(
            service.search_results("python"),
            show_match_rows=True,
        )
        await pilot.pause()

        results = panel.query_one("#search-results", SearchResultsList)
        assert results.options == []


@pytest.mark.asyncio
async def test_idea_list_panel_remaining_branches(
    service: IdeaService,
) -> None:
    """Cover load_ideas compatibility and non-idea/group selections."""
    idea = service.create_idea("Compat idea")
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.query_one("#search-input", Input).value = "compat"
        panel.load_search_results(
            [SearchResult(idea=idea, score=0.0, matches=())],
            show_match_rows=False,
        )
        await pilot.pause()

        panel.load_ideas([idea])
        await pilot.pause()

        tree = panel.query_one("#idea-list", Tree)
        results = panel.query_one("#search-results", SearchResultsList)
        assert not tree.has_class("-hidden")
        assert results.has_class("-hidden")
        assert results.option_count == 0

        panel.query_one("#search-input", Input).value = ""
        await pilot.pause()
        assert panel.select_idea(999999) is False

        # Add malformed idea node to exercise idea_pk is None branch.
        malformed = tree.root.add_leaf("Bad")
        tree.select_node(malformed)
        tree.move_cursor(malformed, animate=False)
        await pilot.pause()
        assert panel.get_selected_idea() is None
        assert panel.get_selected_group_pk() is None

        malformed.data = IdeaTreeNodeData(kind="idea", idea_pk=None)
        tree.select_node(malformed)
        tree.move_cursor(malformed, animate=False)
        await pilot.pause()
        assert panel.get_selected_idea() is None

        panel.load_grouped_ideas(service.list_ideas_grouped())
        tree = panel.query_one("#idea-list", Tree)
        group_node = tree.root.children[0]
        tree.select_node(group_node)
        tree.move_cursor(group_node, animate=False)
        await pilot.pause()
        assert panel.get_selected_group_pk() is not None


@pytest.mark.asyncio
async def test_idea_list_panel_empty_search_results_show_message() -> None:
    """Empty active search should render a non-selectable message row."""
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.query_one("#search-input", Input).value = "no-match"
        panel.load_search_results(
            [],
            show_match_rows=True,
            search_query="no-match",
        )
        await pilot.pause()

        results = panel.query_one("#search-results", SearchResultsList)
        assert results.option_count == 1
        assert results.has_matches() is False
        assert results.get_selected_idea() is None
        assert results.options[0].id == "search-empty-state"
        prompt = results.options[0].prompt
        plain = prompt.plain if hasattr(prompt, "plain") else str(prompt)
        assert plain == 'No results for "no-match"'


@pytest.mark.asyncio
async def test_idea_list_panel_select_group_branches(
    service: IdeaService,
) -> None:
    """Group selection helper should cover missing, success, and search."""
    backend = service.create_group("backend")
    service.create_idea("Grouped", group_pk=backend.pk)
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.load_grouped_ideas(service.list_ideas_grouped())
        await pilot.pause()

        assert panel.select_group(999999) is False
        assert panel.select_group(backend.pk) is True
        assert panel.get_selected_group_pk() == backend.pk

        panel.query_one("#search-input", Input).value = "grouped"
        await pilot.pause()
        assert panel.select_group(backend.pk) is False


@pytest.mark.asyncio
async def test_idea_list_panel_search_autocomplete_flow(
    service: IdeaService,
) -> None:
    """Search autocomplete should chain operator acceptance into values."""
    backend = service.create_group("backend")
    service.create_idea("With python", tags=["python"], group_pk=backend.pk)
    service.create_idea("With api", tags=["api"], group_pk=backend.pk)
    stale_idea = service.create_idea(
        "Temp stale",
        tags=["stale"],
        group_pk=backend.pk,
    )
    service.update_idea(stale_idea.pk, "Temp stale", "", tags=[])

    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.set_autocomplete_sources(
            tags=[tag.name for tag in service.list_tags_in_use()],
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
        assert not autocomplete.has_class("-hidden")
        assert [str(option.prompt) for option in autocomplete.options] == [
            "api",
            "python",
        ]
        assert "stale" not in {
            str(option.prompt) for option in autocomplete.options
        }

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


@pytest.mark.asyncio
async def test_idea_list_panel_group_operator_acceptance_chains() -> None:
    """Accepting `group:` should immediately show matching group values."""
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.set_autocomplete_sources(
            tags=["python"],
            groups=["backend"],
        )
        search = panel.query_one("#search-input", Input)
        autocomplete = panel.query_one("#search-autocomplete", OptionList)

        search.focus()
        await pilot.pause()

        await pilot.press("g")
        await pilot.pause()
        assert [str(option.prompt) for option in autocomplete.options] == [
            "group:",
        ]

        await pilot.press("enter")
        await pilot.pause()
        assert search.value == "group:"
        assert not autocomplete.has_class("-hidden")
        assert [str(option.prompt) for option in autocomplete.options] == [
            "backend",
        ]


@pytest.mark.asyncio
async def test_idea_list_panel_search_autocomplete_extra_branches() -> None:
    """Autocomplete helpers should cover defensive branch paths."""
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.set_autocomplete_sources(
            tags=["python"],
            groups=["backend"],
        )
        search = panel.query_one("#search-input", Input)
        autocomplete = panel.query_one("#search-autocomplete", OptionList)
        search.focus()
        await pilot.pause()

        # Hidden + Shift+Tab should request operator suggestions.
        assert autocomplete.has_class("-hidden")
        await pilot.press("shift+tab")
        await pilot.pause()
        assert not autocomplete.has_class("-hidden")

        # Visible + Escape should dismiss.
        await pilot.press("escape")
        await pilot.pause()
        assert autocomplete.has_class("-hidden")

        # _cycle_autocomplete: count == 0 path.
        autocomplete.set_options([])
        autocomplete.remove_class("-hidden")
        panel._cycle_autocomplete(1)

        # _cycle_autocomplete: highlighted is None path.
        autocomplete.set_options(["tag:"])
        autocomplete.highlighted = None
        panel._cycle_autocomplete(1)
        assert autocomplete.highlighted == 0

        # _apply_highlighted_autocomplete: state is None.
        panel._autocomplete_state = None
        panel._apply_highlighted_autocomplete()

        # _apply_highlighted_autocomplete: highlighted is None.
        panel._autocomplete_state = _AutocompleteState(
            candidates=("tag:",),
            replace_start=0,
            replace_end=0,
        )
        autocomplete.highlighted = None
        panel._apply_highlighted_autocomplete()


@pytest.mark.asyncio
async def test_idea_list_panel_search_keys_can_move_between_input_and_results(
    service: IdeaService,
) -> None:
    """Search should support keyboard-only movement into and out of results."""
    max_wait_ticks = 200
    service.create_idea("Alpha python result")
    service.create_idea("Beta python result")
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.load_grouped_ideas(service.list_ideas_grouped())
        search = panel.query_one("#search-input", Input)
        tree = panel.query_one("#idea-list", Tree)
        results = panel.query_one("#search-results", SearchResultsList)

        search.focus()
        await pilot.pause()
        search.value = "python"
        for _ in range(max_wait_ticks):
            if search.has_class("search-active"):
                break
            await pilot.pause()
        else:
            pytest.fail("Timed out waiting for search-active state")
        panel.load_search_results(
            service.search_results("python"),
            show_match_rows=True,
        )
        await pilot.pause()

        assert search.has_class("search-active")
        assert tree.has_class("search-active")

        await pilot.press("down")
        await pilot.pause()
        assert app.focused is results

        await pilot.press("down")
        await pilot.pause()
        selected = panel.get_selected_idea()
        assert selected is not None
        assert selected.title in {"Alpha python result", "Beta python result"}

        await pilot.press("up")
        await pilot.pause()
        for _ in range(max_wait_ticks):
            if panel.is_first_result_selected():
                break
            await pilot.press("up")
            await pilot.pause()
        else:
            pytest.fail("Timed out returning to the first search result")

        await pilot.press("up")
        await pilot.pause()
        focused = _focused_widget(app)
        assert focused is search

        search.value = ""
        await pilot.pause()
        assert not search.has_class("search-active")
        assert not tree.has_class("search-active")


@pytest.mark.asyncio
async def test_idea_list_panel_search_guard_paths(
    service: IdeaService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guard paths should safely no-op outside active result navigation."""
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.load_grouped_ideas(service.list_ideas_grouped())
        search = panel.query_one("#search-input", Input)
        autocomplete = panel.query_one("#search-autocomplete", OptionList)

        assert panel.focus_results() is False

        search.value = "python"
        autocomplete.remove_class("-hidden")
        await pilot.pause()
        assert panel.focus_results() is False

        autocomplete.add_class("-hidden")
        await pilot.pause()
        assert panel.focus_results() is False

        class _Event:
            def __init__(self) -> None:
                self.key = "left"

            def prevent_default(self) -> None:
                msg = "left should not be consumed"
                raise AssertionError(msg)

            def stop(self) -> None:
                msg = "left should not be stopped"
                raise AssertionError(msg)

        assert (
            panel._handle_result_tree_key(
                cast("Key", _Event()),
                panel.query_one("#search-input", Input),
            )
            is False
        )
        monkeypatch.setattr(panel, "search_is_active", lambda: False)
        assert (
            panel._handle_result_tree_key(
                cast("Key", _Event()),
                panel.query_one("#search-input", Input),
            )
            is False
        )
        panel.check_action("other_action", ())


def test_idea_list_panel_result_navigation_helpers_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Result-navigation helpers should cover empty and boundary cases."""
    panel = IdeaListPanel(id="idea-list-panel")

    class _Results:
        def __init__(self) -> None:
            self._ordered_match_option_ids = ("first", "last")
            self.selection_id = "last"
            self.down_calls = 0
            self.up_calls = 0

        def current_selection(self) -> tuple[str, object]:
            return (self.selection_id, object())

        def action_cursor_down(self) -> None:
            self.down_calls += 1

        def action_cursor_up(self) -> None:
            self.up_calls += 1

        def is_first_match_selected(self) -> bool:
            return self.selection_id == "first"

        def adjacent_match_id(self, direction: int) -> str | None:
            ordered_ids = list(self._ordered_match_option_ids)
            current_index = ordered_ids.index(self.selection_id)
            next_index = current_index + direction
            if next_index < 0 or next_index >= len(ordered_ids):
                return None
            return ordered_ids[next_index]

    results = _Results()
    monkeypatch.setattr(
        panel,
        "query_one",
        lambda selector, *_args, **_kwargs: results,
    )

    assert panel._adjacent_result_node(-1) == "first"
    assert panel._adjacent_result_node(1) is None
    assert panel._move_result_cursor(1) is True
    assert results.down_calls == 1
    assert panel._move_result_cursor(-1) is True
    assert results.up_calls == 1


def test_idea_list_panel_down_key_returns_false_when_search_inactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Down should not be consumed when search is inactive."""
    panel = IdeaListPanel(id="idea-list-panel")

    class _Event:
        prevented = False
        stopped = False

        def prevent_default(self) -> None:
            self.prevented = True

        def stop(self) -> None:
            self.stopped = True

    monkeypatch.setattr(panel, "_autocomplete_is_visible", lambda: False)
    monkeypatch.setattr(panel, "focus_results", lambda: False)
    monkeypatch.setattr(panel, "search_is_active", lambda: False)

    event = _Event()

    assert panel._handle_search_input_down_key(cast("Key", event)) is False
    assert event.prevented is False
    assert event.stopped is False


def test_idea_list_panel_ordered_result_nodes_filters_missing_entries() -> None:
    """Ordered result nodes should keep result order and skip missing nodes."""
    panel = IdeaListPanel(id="idea-list-panel")
    first = _fake_idea_tree_node(line=2, pk=1)
    second = _fake_idea_tree_node(line=8, pk=2)

    panel._idea_nodes_by_pk = {1: first, 2: second}
    panel._result_order_pks = (2, 99, 1)

    assert panel._ordered_result_nodes() == (second, first)


def test_idea_list_panel_widget_helpers_switch_by_search_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Widget helpers should return the tree or results by search state."""
    panel = IdeaListPanel(id="idea-list-panel")

    tree = object()
    results = object()

    def fake_query_one(
        selector: str, *_args: object, **_kwargs: object
    ) -> object:
        if selector == "#idea-list":
            return tree
        if selector == "#search-results":
            return results
        msg = f"unexpected selector: {selector}"
        raise AssertionError(msg)

    monkeypatch.setattr(panel, "query_one", fake_query_one)
    monkeypatch.setattr(panel, "search_is_active", lambda: False)
    assert panel.browse_widget() is tree
    assert panel.active_results_widget() is tree

    monkeypatch.setattr(panel, "search_is_active", lambda: True)
    assert panel.active_results_widget() is results


def test_idea_list_panel_focus_results_returns_false_for_visible_autocomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Visible autocomplete should block focus transfer into results."""
    panel = IdeaListPanel(id="idea-list-panel")

    monkeypatch.setattr(panel, "search_is_active", lambda: True)
    monkeypatch.setattr(panel, "autocomplete_is_visible", lambda: True)

    assert panel.focus_results() is False


@pytest.mark.asyncio
async def test_idea_list_panel_footer_actions_hide_when_search_inactive() -> (
    None
):
    """Search footer hints should disappear when search is not active."""
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        results = panel.query_one("#search-results", SearchResultsList)
        results.focus()
        await pilot.pause()

        assert panel.check_action("footer_next_result", ()) is False


def test_idea_list_panel_truncate_snippet_adds_ellipsis() -> None:
    """Long inline snippets should be compacted with a trailing ellipsis."""
    snippet = "word " * 30
    truncated = _truncate_snippet(snippet)

    assert truncated.endswith("...")
    assert len(truncated) < len(" ".join(snippet.split()))
    assert _truncate_snippet("short snippet") == "short snippet"


@pytest.mark.asyncio
async def test_idea_list_panel_down_key_forces_search_before_focus(
    service: IdeaService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Down in search should fire a pending search before focusing results."""
    service.create_idea("Force search", body="python")
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.load_grouped_ideas(service.list_ideas_grouped())
        search = panel.query_one("#search-input", Input)
        fired: list[str] = []

        monkeypatch.setattr(panel, "focus_results", lambda: False)
        monkeypatch.setattr(panel, "_fire_search", fired.append)

        search.focus()
        search.value = "python"
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()

        assert fired == ["python"]


def test_search_results_widget_helpers_cover_empty_state() -> None:
    """Search-results helpers should handle the empty state cleanly."""
    results = SearchResultsList(id="search-results")

    assert results.has_matches() is False
    assert results.current_selection() is None
    assert results.get_selected_idea() is None
    assert results.get_selected_fragment() is None
    assert results.has_next_match() is False
    assert results.is_first_match_selected() is False
    assert results.adjacent_match_id(1) is None
    assert results.select_first_match_for_idea(1) is False

    results.load_results(
        [],
        show_match_rows=True,
        search_query="no-match",
    )
    assert results.option_count == 1
    assert results.options[0].id == "search-empty-state"
    prompt = results.options[0].prompt
    plain = prompt.plain if hasattr(prompt, "plain") else str(prompt)
    assert plain == 'No results for "no-match"'
    assert results.highlighted is None


def test_search_results_widget_helpers_cover_unmatched_selection_paths() -> (
    None
):
    """Search-results helpers should ignore unmatched highlighted rows."""
    results = SearchResultsList(id="search-results")

    results.set_options([Option("Heading", disabled=True)])
    results.highlighted = 0
    assert results.current_selection() is None
    assert results.is_first_match_selected() is False

    results.set_options([Option("match", id="idea-1-match-0")])
    results.highlighted = 0
    results._selections_by_option_id.clear()
    assert results.current_selection() is None

    results._ordered_match_option_ids = ("idea-1-match-0",)
    results.highlighted = None
    assert results.current_selection() is None


def test_search_results_widget_helpers_cover_adjacent_match_navigation() -> (
    None
):
    """Search-results helpers should navigate adjacent selectable matches."""
    results = SearchResultsList(id="search-results")

    results.set_options(
        [
            Option("match", id="idea-2-match-0"),
            Option("match2", id="idea-2-match-1"),
        ]
    )
    results._ordered_match_option_ids = ("idea-2-match-0", "idea-2-match-1")
    results._selections_by_option_id = {
        "idea-2-match-0": SearchResultSelection(
            idea=cast("Idea", SimpleNamespace()),
            fragment=SearchMatchFragment(source="body", text="a", rank=0),
        ),
        "idea-2-match-1": SearchResultSelection(
            idea=cast("Idea", SimpleNamespace()),
            fragment=SearchMatchFragment(source="body", text="b", rank=1),
        ),
    }
    assert results.select_first_match_for_idea(2) is True
    assert results.has_next_match() is True
    results.highlighted = 1
    assert results.adjacent_match_id(1) is None


def test_search_results_widget_helpers_avoid_idea_id_prefix_collisions() -> (
    None
):
    """Selecting one idea should not collide with a longer idea PK prefix."""
    results = SearchResultsList(id="search-results")

    results.set_options(
        [
            Option("idea 12", id="idea-12"),
            Option("idea 1", id="idea-1"),
        ]
    )
    results._ordered_match_option_ids = ("idea-12", "idea-1")
    results._selections_by_option_id = {
        "idea-12": SearchResultSelection(
            idea=cast("Idea", SimpleNamespace(pk=12)),
            fragment=None,
        ),
        "idea-1": SearchResultSelection(
            idea=cast("Idea", SimpleNamespace(pk=1)),
            fragment=None,
        ),
    }
    assert results.select_first_match_for_idea(1) is True
    assert results.highlighted == results.get_option_index("idea-1")


def test_search_results_widget_can_render_selectable_idea_rows() -> None:
    """Structured-only results should render one selectable row per idea."""
    idea = cast(
        "Idea",
        SimpleNamespace(
            pk=3, title="Tagged", group=SimpleNamespace(name="backend")
        ),
    )
    results = SearchResultsList(id="search-results")

    results.load_results(
        [SearchResult(idea=idea, score=0.0, matches=())],
        show_match_rows=False,
    )

    assert results.has_matches() is True
    assert results.current_selection() is not None
    assert results.get_selected_idea() is idea
    assert results.get_selected_fragment() is None
    assert results.options[0].id == "idea-3"
    prompt = results.options[0].prompt
    assert isinstance(prompt, Text)
    assert prompt.plain == "backend / Tagged"
    assert [(span.start, span.end, span.style) for span in prompt.spans] == [
        (0, 7, "bold"),
        (7, 10, "dim"),
    ]


def test_search_results_widget_renders_group_first_heading_emphasis() -> None:
    """Match headings should show bold group first and plain title second."""
    idea = cast(
        "Idea",
        SimpleNamespace(
            pk=9,
            title="API polish",
            group=SimpleNamespace(name="backend"),
        ),
    )
    results = SearchResultsList(id="search-results")

    results.load_results(
        [
            SearchResult(
                idea=idea,
                score=0.0,
                matches=(
                    SearchMatchFragment(
                        source="body",
                        text="refine API polish",
                        rank=0,
                    ),
                ),
            )
        ],
        show_match_rows=True,
    )

    prompt = results.options[0].prompt
    assert isinstance(prompt, Text)
    assert prompt.plain == "backend / API polish"
    assert [(span.start, span.end, span.style) for span in prompt.spans] == [
        (0, 7, "bold"),
        (7, 10, "dim"),
    ]


def test_search_results_widget_renders_title_once() -> None:
    """Title fragments should only be labelled once in the UI."""
    idea = cast(
        "Idea",
        SimpleNamespace(
            pk=4, title="Python title", group=SimpleNamespace(name="backend")
        ),
    )
    results = SearchResultsList(id="search-results")

    results.load_results(
        [
            SearchResult(
                idea=idea,
                score=0.0,
                matches=(
                    SearchMatchFragment(
                        source="title",
                        text="[[Python]] title",
                        rank=0,
                        is_synthetic=True,
                    ),
                ),
            )
        ],
        show_match_rows=True,
    )

    prompt = results.options[1].prompt
    plain = prompt.plain if hasattr(prompt, "plain") else str(prompt)
    assert plain == "  Title: Python title"


def test_search_results_widget_rejects_unexpected_constructor_kwargs() -> None:
    """Unexpected constructor kwargs should fail loudly."""
    with pytest.raises(TypeError, match="Unexpected keyword arguments: nope"):
        SearchResultsList(nope="value")


def test_search_results_widget_rejects_non_string_id() -> None:
    """Non-string widget ids should be rejected."""
    with pytest.raises(TypeError, match="id must be a string or None"):
        SearchResultsList(id=123)


def test_search_results_widget_event_ignores_unknown_option_ids(
    service: IdeaService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown option IDs should not emit match-selection messages."""
    idea = service.create_idea("Unknown option")
    results = SearchResultsList(id="search-results")
    selection = SearchResultSelection(
        idea=idea,
        fragment=SearchMatchFragment(source="body", text="match", rank=0),
    )
    captured: list[SearchResultSelection] = []
    monkeypatch.setattr(
        results,
        "post_message",
        lambda message: captured.append(message.selection),
    )

    results.on_option_list_option_highlighted(
        cast(
            "OptionList.OptionHighlighted",
            SimpleNamespace(option_id=None),
        )
    )
    results.on_option_list_option_selected(
        cast(
            "OptionList.OptionSelected",
            SimpleNamespace(option_id=None),
        )
    )
    results.on_option_list_option_selected(
        cast(
            "OptionList.OptionSelected",
            SimpleNamespace(option_id="missing"),
        )
    )
    results.on_option_list_option_highlighted(
        cast(
            "OptionList.OptionHighlighted",
            SimpleNamespace(option_id="missing"),
        )
    )
    results._selections_by_option_id["known"] = selection
    results.on_option_list_option_selected(
        cast(
            "OptionList.OptionSelected",
            SimpleNamespace(option_id="known"),
        )
    )

    assert captured == [selection]


def test_marked_text_to_text_handles_unclosed_marker() -> None:
    """Unclosed highlight markers should fall back to plain text append."""
    rendered = _marked_text_to_text("prefix [[broken")

    assert rendered.plain == "prefix [[broken"


@pytest.mark.asyncio
async def test_idea_list_panel_blur_defers_for_option_selection() -> None:
    """Search blur should defer dismissal while option list takes focus."""
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.set_autocomplete_sources(tags=["python"], groups=["backend"])
        search = panel.query_one("#search-input", Input)
        autocomplete = panel.query_one("#search-autocomplete", OptionList)

        search.focus()
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        assert not autocomplete.has_class("-hidden")

        autocomplete.focus()
        await pilot.pause()

        panel.on_input_blurred(Input.Blurred(search, search.value))
        await pilot.pause()
        assert not autocomplete.has_class("-hidden")

        search.value = ""
        search.cursor_position = 0
        search.focus()
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        assert not autocomplete.has_class("-hidden")

        panel.on_option_list_option_selected(
            OptionList.OptionSelected(
                autocomplete,
                autocomplete.options[0],
                0,
            ),
        )
        await pilot.pause()

        assert search.value == "tag:"
        assert not autocomplete.has_class("-hidden")
        assert [str(option.prompt) for option in autocomplete.options] == [
            "python",
        ]
        assert app.focused is search


@pytest.mark.asyncio
async def test_idea_list_panel_autocomplete_blur_descendant_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dismiss helper should keep popup open for focused descendants."""
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.set_autocomplete_sources(tags=["python"], groups=["backend"])
        search = panel.query_one("#search-input", Input)
        autocomplete = panel.query_one("#search-autocomplete", OptionList)

        search.focus()
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        assert not autocomplete.has_class("-hidden")

        class _FocusedDescendant:
            @property
            def ancestors(self) -> list[OptionList]:
                return [autocomplete]

        monkeypatch.setattr(
            type(app),
            "focused",
            property(lambda _self: _FocusedDescendant()),
        )
        panel._dismiss_autocomplete_if_unfocused()
        assert not autocomplete.has_class("-hidden")


@pytest.mark.asyncio
async def test_idea_list_panel_option_selected_ignores_other_option_lists() -> (
    None
):
    """OptionSelected from unrelated lists should be ignored."""
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.set_autocomplete_sources(tags=["python"], groups=["backend"])
        search = panel.query_one("#search-input", Input)
        autocomplete = panel.query_one("#search-autocomplete", OptionList)

        search.focus()
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        assert not autocomplete.has_class("-hidden")
        before = search.value

        foreign = OptionList("noop", id="other-autocomplete")
        panel.on_option_list_option_selected(
            OptionList.OptionSelected(
                foreign,
                foreign.options[0],
                0,
            ),
        )
        await pilot.pause()

        assert search.value == before
        assert not autocomplete.has_class("-hidden")


def test_idea_list_panel_apply_highlighted_out_of_range_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Out-of-range highlight should safely no-op."""
    panel = IdeaListPanel(id="idea-list-panel")
    panel._autocomplete_state = _AutocompleteState(
        candidates=("tag:",),
        replace_start=0,
        replace_end=0,
    )

    class _FakeAutocomplete:
        highlighted = 3

    fake_autocomplete = _FakeAutocomplete()

    def fake_query_one(
        selector: str,
        *_args: object,
        **_kwargs: object,
    ) -> object:
        if selector == "#search-autocomplete":
            return fake_autocomplete
        msg = f"Unexpected query selector: {selector}"
        raise AssertionError(msg)

    monkeypatch.setattr(
        panel,
        "query_one",
        fake_query_one,
    )
    panel._apply_highlighted_autocomplete()


def test_idea_list_panel_autocomplete_pure_helpers_branches() -> None:
    """Pure autocomplete helpers should cover unsupported/no-match paths."""
    assert (
        _resolve_autocomplete_state(
            "foo:bar",
            cursor_position=7,
            tags=("python",),
            groups=("backend",),
            allow_empty_operator=True,
        )
        is None
    )

    assert (
        _resolve_autocomplete_state(
            "tag:zzz",
            cursor_position=7,
            tags=("python",),
            groups=("backend",),
            allow_empty_operator=True,
        )
        is None
    )

    assert (
        _resolve_autocomplete_state(
            "tag:python",
            cursor_position=2,
            tags=("python",),
            groups=("backend",),
            allow_empty_operator=True,
        )
        is None
    )

    start, end = _token_bounds("tag:python and", 1)
    assert (start, end) == (0, 10)


def test_idea_list_panel_get_selected_idea_with_missing_pk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inactive search should still use the tree selection path."""
    panel = IdeaListPanel(id="idea-list-panel")

    class _Node:
        data = IdeaTreeNodeData(kind="idea", idea_pk=None)

    class _Tree:
        cursor_node = _Node()

    monkeypatch.setattr(panel, "search_is_active", lambda: False)
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
        assert body.source != ""

        view.show_empty()
        await pilot.pause()

        assert str(title.content) == ""
        assert str(tags.content) == ""
        assert str(timestamps.content) == ""
        assert "Select an idea from the list" in body.source


@pytest.mark.asyncio
async def test_idea_view_skips_same_hash_markdown_update(
    service: IdeaService,
    mocker: MockerFixture,
) -> None:
    """Showing the same idea hash should not re-render Markdown."""
    idea = service.create_idea("Stable", body="Body text")
    view = IdeaView(id="content-panel")
    app = _WidgetApp(view)

    async with app.run_test() as pilot:
        view.show_idea(idea)
        await pilot.pause()

        body = view.query_one("#idea-view-body", Markdown)
        update = mocker.patch.object(body, "update")

        same_hash_idea = service.get_idea(idea.pk)
        assert same_hash_idea is not None
        assert same_hash_idea is not idea

        view.show_idea(same_hash_idea)
        await pilot.pause()

        update.assert_not_called()


@pytest.mark.asyncio
async def test_idea_view_tags_have_click_markup(
    service: IdeaService,
) -> None:
    """Tags should render with @click markup for search-by-tag."""
    idea = service.create_idea(
        "Clickable",
        body="Body text",
        tags=["python", "testing"],
    )
    view = IdeaView(id="content-panel")
    app = _WidgetApp(view)

    async with app.run_test() as pilot:
        view.show_idea(idea)
        await pilot.pause()

        tags = view.query_one("#idea-view-tags", Static)
        content = str(tags.content)
        assert "search_by_tag" in content
        assert "python" in content
        assert "testing" in content


def test_tag_click_markup_plain() -> None:
    """Normal tag names produce @click markup."""
    result = _tag_click_markup("python")
    assert "search_by_tag('python')" in result
    assert "python" in result


def test_tag_click_markup_with_bracket() -> None:
    """Tag names containing brackets fall back to escaped plain text."""
    result = _tag_click_markup("tag]name")
    assert "search_by_tag" not in result
    assert "tag]name" in result


def test_tag_click_markup_with_open_bracket() -> None:
    """Tag names containing [ fall back to escaped plain text."""
    result = _tag_click_markup("tag[name")
    assert "search_by_tag" not in result
    assert "tag\\[name" in result
    assert result.startswith("\\[")


def test_tag_click_markup_escapes_quotes() -> None:
    """Single quotes in tag names are escaped in the action string."""
    result = _tag_click_markup("it's")
    assert "\\'" in result
    assert "search_by_tag" in result


@pytest.mark.asyncio
async def test_set_search_query_updates_input() -> None:
    """set_search_query sets the search value and focuses the input."""
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.set_search_query("tag:python")
        await pilot.pause()

        search = panel.query_one("#search-input", Input)
        assert search.value == "tag:python"
        assert search.has_focus
        assert search.cursor_position == len("tag:python")

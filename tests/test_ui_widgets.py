"""Tests for UI widgets."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input, Markdown, OptionList, Static, Tree

from cogitus.search import SearchResult
from cogitus.ui.widgets.idea_list import (
    IdeaListPanel,
    IdeaTreeNodeData,
    _AutocompleteState,
    _format_timestamp,
    _resolve_autocomplete_state,
    _token_bounds,
    _truncate_snippet,
)
from cogitus.ui.widgets.idea_view import IdeaView, _format_full_timestamp

if TYPE_CHECKING:
    from pytest_mock import MockerFixture
    from textual.events import Key
    from textual.widget import Widget
    from textual.widgets.tree import TreeNode

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
async def test_idea_list_panel_renders_search_snippets(
    service: IdeaService,
) -> None:
    """Search-result loading should include per-row snippets."""
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
            ]
        )
        await pilot.pause()

        tree = panel.query_one("#idea-list", Tree)
        node_label = tree.root.children[0].children[0].label
        plain = getattr(node_label, "plain", str(node_label))

        assert "Snippet target" in plain
        assert "searchable body snippet for python" in plain


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

        await pilot.press("tab")
        await pilot.pause()
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
    service.create_idea("Alpha python result")
    service.create_idea("Beta python result")
    panel = IdeaListPanel(id="idea-list-panel")
    app = _WidgetApp(panel)

    async with app.run_test() as pilot:
        panel.load_grouped_ideas(service.list_ideas_grouped())
        search = panel.query_one("#search-input", Input)
        tree = panel.query_one("#idea-list", Tree)

        search.focus()
        await pilot.pause()
        search.value = "python"
        await pilot.pause()

        assert search.has_class("search-active")
        assert tree.has_class("search-active")

        await pilot.press("down")
        await pilot.pause()
        assert app.focused is tree

        await pilot.press("down")
        await pilot.pause()
        selected = panel.get_selected_idea()
        assert selected is not None
        assert selected.title == "Alpha python result"

        await pilot.press("up")
        await pilot.pause()
        selected = panel.get_selected_idea()
        assert selected is not None
        assert selected.title == "Beta python result"

        await pilot.press("up")
        await pilot.pause()
        assert app.focused is search

        search.value = ""
        await pilot.pause()
        assert not search.has_class("search-active")
        assert not tree.has_class("search-active")


@pytest.mark.asyncio
async def test_idea_list_panel_search_guard_paths(
    service: IdeaService,
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
        panel.check_action("other_action", ())


def test_idea_list_panel_result_navigation_helpers_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Result-navigation helpers should cover empty and boundary cases."""
    panel = IdeaListPanel(id="idea-list-panel")

    class _Tree:
        def __init__(self, cursor_line: int) -> None:
            self.cursor_line = cursor_line
            self.cursor_node: TreeNode[IdeaTreeNodeData] | None = None
            self.moved_to: TreeNode[IdeaTreeNodeData] | None = None
            self.root = SimpleNamespace(children=[])

        def move_cursor(
            self,
            node: TreeNode[IdeaTreeNodeData],
            *,
            animate: bool,
        ) -> None:
            assert animate is False
            self.cursor_node = node
            self.moved_to = node

    tree = _Tree(cursor_line=-1)
    monkeypatch.setattr(
        panel,
        "query_one",
        lambda selector, *_args, **_kwargs: tree,
    )

    assert panel._adjacent_result_node(1) is None
    assert panel._move_result_cursor(1) is True

    first = _fake_idea_tree_node(line=2, pk=1)
    last = _fake_idea_tree_node(line=8, pk=2)
    panel._idea_nodes_by_pk = {1: first, 2: last}
    panel._result_order_pks = (1, 2)

    assert panel._adjacent_result_node(-1) is last
    assert panel._adjacent_result_node(1) is first

    tree.cursor_line = last.line
    tree.cursor_node = last
    tree.moved_to = None
    monkeypatch.setattr(
        panel,
        "get_selected_idea",
        lambda: SimpleNamespace(pk=2),
    )
    assert panel._move_result_cursor(1) is True
    assert tree.moved_to is None


def test_idea_list_panel_ordered_result_nodes_filters_missing_entries() -> None:
    """Ordered result nodes should keep result order and skip missing nodes."""
    panel = IdeaListPanel(id="idea-list-panel")
    first = _fake_idea_tree_node(line=2, pk=1)
    second = _fake_idea_tree_node(line=8, pk=2)

    panel._idea_nodes_by_pk = {1: first, 2: second}
    panel._result_order_pks = (2, 99, 1)

    assert panel._ordered_result_nodes() == (second, first)


def test_idea_list_panel_focus_results_returns_false_for_visible_autocomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Visible autocomplete should block focus transfer into results."""
    panel = IdeaListPanel(id="idea-list-panel")

    monkeypatch.setattr(panel, "search_is_active", lambda: True)
    monkeypatch.setattr(panel, "autocomplete_is_visible", lambda: True)

    assert panel.focus_results() is False


def test_idea_list_panel_truncate_snippet_adds_ellipsis() -> None:
    """Long inline snippets should be compacted with a trailing ellipsis."""
    snippet = "word " * 30
    truncated = _truncate_snippet(snippet)

    assert truncated.endswith("...")
    assert len(truncated) < len(" ".join(snippet.split()))


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
        assert autocomplete.has_class("-hidden")
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

"""Left pane: grouped idea tree with search."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar, Literal

from rich.text import Text
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, OptionList, Tree

from cogitus.ui.widgets.autocomplete import (
    _AutocompleteState,
    apply_highlighted_autocomplete,
    autocomplete_is_visible,
    cycle_autocomplete,
    dismiss_autocomplete,
    should_keep_autocomplete_open,
    show_autocomplete,
)
from cogitus.ui.widgets.search_results import SearchResultsList

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.events import Key
    from textual.timer import Timer
    from textual.widget import Widget
    from textual.widgets.tree import TreeNode

    from cogitus.models.group import Group
    from cogitus.models.idea import Idea
    from cogitus.search import SearchResult

_DAYS_IN_WEEK = 7
_MAX_SNIPPET_LENGTH = 88
_SEARCH_OPERATORS: tuple[str, ...] = ("tag:", "group:")


@dataclass(frozen=True)
class IdeaTreeNodeData:
    """Typed metadata for tree nodes."""

    kind: Literal["root", "group", "idea"]
    group_pk: int | None = None
    idea_pk: int | None = None


@dataclass(frozen=True)
class _TokenContext:
    """Token metadata around the current search cursor position."""

    token: str
    token_start: int
    token_end: int
    relative_cursor: int
    colon_at: int


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


def _format_group_label(name: str, idea_count: int) -> Text:
    """Build a group label with stronger emphasis and a dimmed count."""
    label = Text(name, style="bold")
    label.append(f" ({idea_count})", style="not bold dim")
    return label


def _format_idea_label(idea: Idea) -> Text:
    """Build an idea label with a secondary timestamp suffix."""
    ts = _format_timestamp(idea.updated_at)
    label = Text(idea.title)
    if ts:
        label.append(f" [{ts}]", style="dim")
    return label


class IdeaListPanel(Vertical):
    """Left panel with search input and grouped idea tree."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            "down",
            "footer_next_result",
            "Next Result",
            show=True,
            key_display="Down",
            priority=True,
        ),
        Binding(
            "up",
            "footer_previous_result",
            "Prev Result",
            show=True,
            key_display="Up",
            priority=True,
        ),
        Binding(
            "escape",
            "footer_back_to_search",
            "Back to Search",
            show=True,
            key_display="Esc",
            priority=True,
        ),
    ]

    class IdeaSelected(Message):
        """Fired when an idea is selected."""

        def __init__(self, idea: Idea) -> None:
            """Initialize with the selected idea."""
            self.idea = idea
            super().__init__()

    class SearchChanged(Message):
        """Fired when search query changes (debounced)."""

        def __init__(self, query: str) -> None:
            """Initialize with the search query."""
            self.query = query
            super().__init__()

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
    ) -> None:
        """Initialize the idea list panel."""
        super().__init__(name=name, id=id, classes=classes)
        self._debounce_timer: Timer | None = None
        self._ideas_by_pk: dict[int, Idea] = {}
        self._group_nodes_by_pk: dict[int, TreeNode[IdeaTreeNodeData]] = {}
        self._idea_nodes_by_pk: dict[int, TreeNode[IdeaTreeNodeData]] = {}
        self._result_order_pks: tuple[int, ...] = ()
        self._tag_suggestions: tuple[str, ...] = ()
        self._group_suggestions: tuple[str, ...] = ()
        self._autocomplete_state: _AutocompleteState | None = None
        self._suspend_autocomplete_sync = False

    def compose(self) -> ComposeResult:
        """Compose the idea list panel."""
        yield Input(
            placeholder="Search (text, tag:foo, group:bar)",
            id="search-input",
        )
        yield OptionList(id="search-autocomplete", classes="-hidden")
        tree = Tree[IdeaTreeNodeData](
            "Ideas",
            data=IdeaTreeNodeData(kind="root"),
            id="idea-list",
        )
        tree.show_root = False
        yield tree
        yield SearchResultsList(id="search-results", classes="-hidden")

    def _reset_tree(self) -> Tree[IdeaTreeNodeData]:
        """Clear tree and internal state, returning the tree widget."""
        tree = self.query_one("#idea-list", Tree)
        tree.clear()
        self._ideas_by_pk.clear()
        self._group_nodes_by_pk.clear()
        self._idea_nodes_by_pk.clear()
        self._result_order_pks = ()
        tree.root.label = "Ideas"
        tree.root.data = IdeaTreeNodeData(kind="root")
        return tree

    def load_grouped_ideas(
        self,
        grouped_ideas: list[tuple[Group, list[Idea]]],
        *,
        auto_select_first: bool = True,
    ) -> None:
        """Replace the displayed grouped ideas."""
        tree = self._reset_tree()
        self._show_tree_mode()
        self.query_one("#search-results", SearchResultsList).clear_results()
        first_idea_node: TreeNode[IdeaTreeNodeData] | None = None
        ordered_pks: list[int] = []
        for group, ideas in grouped_ideas:
            group_node = tree.root.add(
                _format_group_label(group.name, len(ideas)),
                data=IdeaTreeNodeData(kind="group", group_pk=group.pk),
                expand=True,
            )
            self._group_nodes_by_pk[group.pk] = group_node
            for idea in ideas:
                idea_node = self._add_idea_node(
                    group_node,
                    idea,
                    group_pk=group.pk,
                )
                if first_idea_node is None:
                    first_idea_node = idea_node
                ordered_pks.append(idea.pk)
        self._result_order_pks = tuple(ordered_pks)
        tree.root.expand()
        if auto_select_first and first_idea_node is not None:
            tree.select_node(first_idea_node)
            tree.move_cursor(first_idea_node, animate=False)
        else:
            tree.unselect()

    def load_grouped_search_results(
        self,
        grouped_results: list[tuple[Group, list[SearchResult]]],
        *,
        show_match_rows: bool = True,
    ) -> None:
        """Compatibility helper that flattens grouped search results."""
        results: list[SearchResult] = []
        for _group, group_results in grouped_results:
            results.extend(group_results)
        self.load_search_results(
            results,
            show_match_rows=show_match_rows,
        )

    def load_search_results(
        self,
        results: list[SearchResult],
        *,
        show_match_rows: bool = True,
    ) -> None:
        """Replace the active-search view with dedicated search results."""
        self._show_search_results_mode()
        tree = self._reset_tree()
        tree.root.expand()
        for result in results:
            self._ideas_by_pk[result.idea.pk] = result.idea
        search_results = self.query_one("#search-results", SearchResultsList)
        search_results.load_results(
            results,
            show_match_rows=show_match_rows,
        )

    def load_ideas(self, ideas: list[Idea]) -> None:
        """Compatibility helper to load ideas under a synthetic group."""
        tree = self._reset_tree()
        self._show_tree_mode()
        self.query_one("#search-results", SearchResultsList).clear_results()
        first_idea_node: TreeNode[IdeaTreeNodeData] | None = None
        ordered_pks: list[int] = []
        for idea in ideas:
            idea_node = self._add_idea_node(
                tree.root,
                idea,
            )
            if first_idea_node is None:
                first_idea_node = idea_node
            ordered_pks.append(idea.pk)
        self._result_order_pks = tuple(ordered_pks)
        tree.root.expand()
        if first_idea_node is not None:
            tree.select_node(first_idea_node)
            tree.move_cursor(first_idea_node, animate=False)

    def _add_idea_node(
        self,
        parent: TreeNode[IdeaTreeNodeData],
        idea: Idea,
        *,
        group_pk: int | None = None,
    ) -> TreeNode[IdeaTreeNodeData]:
        """Add an idea leaf node under parent and track it by primary key."""
        label = _format_idea_label(idea)
        node = parent.add_leaf(
            label,
            data=IdeaTreeNodeData(
                kind="idea",
                group_pk=group_pk,
                idea_pk=idea.pk,
            ),
        )
        self._ideas_by_pk[idea.pk] = idea
        self._idea_nodes_by_pk[idea.pk] = node
        return node

    def select_idea(self, idea_pk: int) -> bool:
        """Select an idea node by primary key."""
        if self.search_is_active():
            results = self.query_one("#search-results", SearchResultsList)
            selected = results.select_first_match_for_idea(idea_pk)
            if selected:
                self.refresh_bindings()
            return selected
        tree = self.query_one("#idea-list", Tree)
        node = self._idea_nodes_by_pk.get(idea_pk)
        if node is None:
            return False
        tree.select_node(node)
        tree.move_cursor(node, animate=False)
        self.refresh_bindings()
        return True

    def select_group(self, group_pk: int) -> bool:
        """Select a group node by primary key."""
        if self.search_is_active():
            return False
        tree = self.query_one("#idea-list", Tree)
        node = self._group_nodes_by_pk.get(group_pk)
        if node is None:
            return False
        tree.select_node(node)
        tree.move_cursor(node, animate=False)
        self.refresh_bindings()
        return True

    def get_selected_idea(self) -> Idea | None:
        """Return the currently selected idea."""
        if self.search_is_active():
            return self.query_one(
                "#search-results",
                SearchResultsList,
            ).get_selected_idea()
        tree = self.query_one("#idea-list", Tree)
        if getattr(tree, "cursor_line", 0) == -1:
            return None
        node = tree.cursor_node
        data = node.data if node is not None else None
        if not isinstance(data, IdeaTreeNodeData) or data.kind != "idea":
            return None
        if data.idea_pk is None:
            return None
        return self._ideas_by_pk.get(data.idea_pk)

    def get_selected_group_pk(self) -> int | None:
        """Return selected group pk when a group node is selected."""
        if self.search_is_active():
            return None
        tree = self.query_one("#idea-list", Tree)
        if getattr(tree, "cursor_line", 0) == -1:
            return None
        node = tree.cursor_node
        data = node.data if node is not None else None
        if not isinstance(data, IdeaTreeNodeData) or data.kind != "group":
            return None
        return data.group_pk

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes with debounce."""
        if event.input.id == "search-input":
            self._sync_search_state_classes()
            if self._suspend_autocomplete_sync:
                # Assumes Textual Input emits exactly one synchronous
                # Input.Changed per programmatic search.value assignment.
                self._suspend_autocomplete_sync = False
            else:
                self._sync_autocomplete()
            if self._debounce_timer is not None:
                self._debounce_timer.stop()
            self._debounce_timer = self.set_timer(
                0.2,
                lambda: self._fire_search(event.value),
            )
            self.refresh_bindings()

    def on_input_blurred(self, event: Input.Blurred) -> None:
        """Hide autocomplete when search input loses focus."""
        if event.input.id == "search-input":
            self.call_later(self._dismiss_autocomplete_if_unfocused)

    def _dismiss_autocomplete_if_unfocused(self) -> None:
        """Dismiss autocomplete unless focus moved to search/options list."""
        search = self.query_one("#search-input", Input)
        autocomplete = self.query_one("#search-autocomplete", OptionList)
        if should_keep_autocomplete_open(
            focused=self.app.focused,
            input_widget=search,
            autocomplete=autocomplete,
        ):
            return
        self.dismiss_autocomplete()

    def on_option_list_option_selected(
        self,
        event: OptionList.OptionSelected,
    ) -> None:
        """Apply selected autocomplete candidate and restore search focus."""
        if event.option_list.id != "search-autocomplete":
            return
        self._apply_highlighted_autocomplete()
        self.query_one("#search-input", Input).focus()
        event.stop()

    def on_search_results_list_match_highlighted(
        self,
        event: SearchResultsList.MatchHighlighted,
    ) -> None:
        """Propagate search-result highlight changes as idea selections."""
        self.refresh_bindings()
        if self.app.focused is self.query_one(
            "#search-results",
            SearchResultsList,
        ):
            self.post_message(self.IdeaSelected(event.selection.idea))

    def _fire_search(self, query: str) -> None:
        """Post the debounced search message."""
        self.post_message(self.SearchChanged(query))

    def on_tree_node_selected(
        self,
        event: Tree.NodeSelected[IdeaTreeNodeData],
    ) -> None:
        """Handle idea selection from tree."""
        self.refresh_bindings()
        self._post_if_idea_node(event.node.data)

    def on_tree_node_highlighted(
        self,
        event: Tree.NodeHighlighted[IdeaTreeNodeData],
    ) -> None:
        """Handle highlight change in tree."""
        self.refresh_bindings()
        data = event.node.data if event.node is not None else None
        self._post_if_idea_node(data)

    def _post_if_idea_node(self, data: IdeaTreeNodeData | None) -> None:
        """Post IdeaSelected if data represents a valid idea node."""
        if (
            data is not None
            and data.kind == "idea"
            and data.idea_pk is not None
            and data.idea_pk in self._ideas_by_pk
        ):
            self.post_message(
                self.IdeaSelected(self._ideas_by_pk[data.idea_pk])
            )

    def focus_search(self) -> None:
        """Focus the search input."""
        self.query_one("#search-input", Input).focus()

    def is_search_input_focused(self) -> bool:
        """Return whether the search input currently has focus."""
        return self.app.focused is self.query_one("#search-input", Input)

    def is_search_results_focused(self) -> bool:
        """Return whether the search results list currently has focus."""
        return self.app.focused is self.query_one(
            "#search-results",
            SearchResultsList,
        )

    def current_search_query(self) -> str:
        """Return the trimmed current search query."""
        return self.raw_search_query().strip()

    def raw_search_query(self) -> str:
        """Return the raw current search input value."""
        return self.query_one("#search-input", Input).value

    def focus_results(self) -> bool:
        """Focus the active search-results list when it has selectable rows."""
        if not self.search_is_active():
            return False
        if self.autocomplete_is_visible():
            return False
        results = self.query_one("#search-results", SearchResultsList)
        if not results.has_matches():
            return False
        results.focus()
        selected = results.get_selected_idea()
        if selected is not None:
            self.post_message(self.IdeaSelected(selected))
        return True

    def focus_preferred_list_widget(self) -> None:
        """Focus the correct list-side widget for the current search state."""
        if self.focus_results():
            return
        if self.search_is_active():
            self.query_one("#search-input", Input).focus()
            return
        self.browse_widget().focus()

    def clear_search(self) -> None:
        """Clear the search input."""
        search = self.query_one("#search-input", Input)
        search.value = ""
        self.dismiss_autocomplete()
        search.focus()

    def cancel_search_interaction(
        self,
    ) -> Literal[
        "closed_autocomplete",
        "focused_search",
        "cleared_search",
        "noop",
    ]:
        """Handle `Esc` within the list panel's search UI."""
        if self.dismiss_autocomplete():
            return "closed_autocomplete"
        if self.is_search_results_focused() and self.search_is_active():
            self.focus_search()
            return "focused_search"
        if not self.is_search_input_focused():
            return "noop"
        self.clear_search()
        return "cleared_search"

    def search_is_active(self) -> bool:
        """Return whether the search input currently contains a query."""
        return bool(self.raw_search_query())

    def autocomplete_is_visible(self) -> bool:
        """Return whether search autocomplete is currently visible."""
        return self._autocomplete_is_visible()

    def is_first_result_selected(self) -> bool:
        """Return whether the first active search result is selected."""
        return self._tree_cursor_is_first_result()

    def set_autocomplete_sources(
        self,
        *,
        tags: list[str],
        groups: list[str],
    ) -> None:
        """Set the candidate values used for search autocomplete."""
        self._tag_suggestions = tuple(_normalize_suggestions(tags))
        self._group_suggestions = tuple(_normalize_suggestions(groups))
        self._sync_autocomplete()

    def on_key(self, event: Key) -> None:
        """Handle search-input and active-search result navigation keys."""
        search = self.query_one("#search-input", Input)
        results = self.query_one("#search-results", SearchResultsList)
        if self.app.focused is results and self._handle_result_tree_key(
            event,
            search,
        ):
            return

        if self.app.focused is not search:
            return

        self._handle_search_input_key(event)

    def _handle_result_tree_key(
        self,
        event: Key,
        search: Input,
    ) -> bool:
        """Handle keys while the search-results list is focused."""
        if (
            not self.search_is_active()
            or event.key != "up"
            or not self._tree_cursor_is_first_result()
        ):
            return False
        event.prevent_default()
        event.stop()
        search.focus()
        return True

    def _handle_search_input_key(self, event: Key) -> None:
        """Handle keys while the search input is focused."""
        if event.key == "tab":
            self._handle_autocomplete_cycle(event, 1)
            return

        if event.key in {"shift+tab", "backtab"}:
            self._handle_autocomplete_cycle(event, -1)
            return

        if event.key == "up" and self._autocomplete_is_visible():
            self._cycle_visible_autocomplete(event, -1)
            return

        if event.key == "down" and self._handle_search_input_down_key(event):
            return

        if event.key == "enter" and self._autocomplete_is_visible():
            event.prevent_default()
            event.stop()
            self._apply_highlighted_autocomplete()
            return

        if event.key == "escape" and self._autocomplete_is_visible():
            event.prevent_default()
            event.stop()
            self.dismiss_autocomplete()

    def _handle_search_input_down_key(self, event: Key) -> bool:
        """Handle `Down` from the search input across autocomplete/results."""
        if self._autocomplete_is_visible():
            self._cycle_visible_autocomplete(event, 1)
            return True
        if self.focus_results():
            event.prevent_default()
            event.stop()
            return True
        if not self.search_is_active():
            return False

        event.prevent_default()
        event.stop()
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
        search = self.query_one("#search-input", Input)
        self._fire_search(search.value)
        self.call_later(self.focus_results)
        return True

    def _handle_autocomplete_cycle(
        self,
        event: Key,
        direction: Literal[-1, 1],
    ) -> None:
        """Handle cycling autocomplete or opening operator suggestions."""
        if self._autocomplete_is_visible():
            self._cycle_visible_autocomplete(event, direction)
            return
        event.prevent_default()
        event.stop()
        self._sync_autocomplete(allow_empty_operator=True)

    def _cycle_visible_autocomplete(
        self,
        event: Key,
        direction: Literal[-1, 1],
    ) -> None:
        """Cycle autocomplete and consume the triggering key event."""
        event.prevent_default()
        event.stop()
        self._cycle_autocomplete(direction)

    def dismiss_autocomplete(self) -> bool:
        """Close autocomplete popup if it is currently visible."""
        autocomplete = self.query_one("#search-autocomplete", OptionList)
        if not dismiss_autocomplete(autocomplete):
            return False
        self._autocomplete_state = None
        return True

    def _autocomplete_is_visible(self) -> bool:
        """Return whether autocomplete popup is currently visible."""
        autocomplete = self.query_one("#search-autocomplete", OptionList)
        return autocomplete_is_visible(autocomplete)

    def _sync_autocomplete(self, *, allow_empty_operator: bool = False) -> None:
        """Recompute autocomplete state from current search/cursor context."""
        search = self.query_one("#search-input", Input)
        state = _resolve_autocomplete_state(
            search.value,
            cursor_position=search.cursor_position,
            tags=self._tag_suggestions,
            groups=self._group_suggestions,
            allow_empty_operator=allow_empty_operator,
        )
        if state is None:
            self.dismiss_autocomplete()
            return
        self._autocomplete_state = state
        autocomplete = self.query_one("#search-autocomplete", OptionList)
        show_autocomplete(autocomplete, state)

    def _cycle_autocomplete(self, direction: Literal[-1, 1]) -> None:
        """Move autocomplete highlight forward or backward with wrapping."""
        autocomplete = self.query_one("#search-autocomplete", OptionList)
        cycle_autocomplete(autocomplete, direction)

    def _apply_highlighted_autocomplete(self) -> None:
        """Apply the currently highlighted autocomplete candidate."""
        state = self._autocomplete_state
        autocomplete = self.query_one("#search-autocomplete", OptionList)
        highlighted = autocomplete.highlighted
        if state is None or highlighted is None:
            return
        if highlighted >= len(state.candidates):
            return
        search = self.query_one("#search-input", Input)
        apply_highlighted_autocomplete(
            state=state,
            autocomplete=autocomplete,
            input_widget=search,
            before_input_change=self._suspend_autocomplete_sync_once,
        )

    def _suspend_autocomplete_sync_once(self) -> None:
        """Suppress the next programmatic Input.Changed event."""
        # Matches on_input_changed assumption: one sync Input.Changed event.
        self._suspend_autocomplete_sync = True

    def _sync_search_state_classes(self) -> None:
        """Apply active-search styling classes to input and tree."""
        search = self.query_one("#search-input", Input)
        tree = self.query_one("#idea-list", Tree)
        results = self.query_one("#search-results", SearchResultsList)
        if self.search_is_active():
            search.add_class("search-active")
            tree.add_class("search-active")
            results.add_class("search-active")
            return
        search.remove_class("search-active")
        tree.remove_class("search-active")
        results.remove_class("search-active")

    def _tree_cursor_is_first_result(self) -> bool:
        """Return whether the first selectable active-search row is selected."""
        results = self.query_one("#search-results", SearchResultsList)
        return results.is_first_match_selected()

    def _move_result_cursor(self, direction: Literal[-1, 1]) -> bool:
        """Move the active search-results cursor to the previous/next row."""
        results = self.query_one("#search-results", SearchResultsList)
        if direction > 0:
            results.action_cursor_down()
        else:
            results.action_cursor_up()
        return True

    def _adjacent_result_node(
        self,
        direction: Literal[-1, 1],
    ) -> object | None:
        """Return a placeholder when a previous/next search result exists."""
        results = self.query_one("#search-results", SearchResultsList)
        return results.adjacent_match_id(direction)

    def _ordered_result_nodes(self) -> tuple[TreeNode[IdeaTreeNodeData], ...]:
        """Return result idea nodes ordered by their current tree position."""
        return tuple(
            self._idea_nodes_by_pk[pk]
            for pk in self._result_order_pks
            if pk in self._idea_nodes_by_pk
        )

    def check_action(
        self,
        action: str,
        parameters: tuple[object, ...],
    ) -> bool | None:
        """Show footer hints only while navigating active search results."""
        footer_actions = {
            "footer_next_result",
            "footer_previous_result",
            "footer_back_to_search",
        }
        if action not in footer_actions:
            return super().check_action(action, parameters)

        if self.app.focused is not self.query_one(
            "#search-results",
            SearchResultsList,
        ):
            return False
        if not self.search_is_active():
            return False

        result: bool | None = None
        if action == "footer_next_result":
            result = self._adjacent_result_node(1) is not None
        elif action in {"footer_previous_result", "footer_back_to_search"}:
            result = True
        return result

    def browse_widget(self) -> Widget:
        """Return the normal browsing widget."""
        return self.query_one("#idea-list", Tree)

    def active_results_widget(self) -> Widget:
        """Return the currently active list-side focus target."""
        if self.search_is_active():
            return self.query_one("#search-results", SearchResultsList)
        return self.query_one("#idea-list", Tree)

    def _show_tree_mode(self) -> None:
        """Show the normal tree and hide dedicated search results."""
        tree = self.query_one("#idea-list", Tree)
        results = self.query_one("#search-results", SearchResultsList)
        tree.remove_class("-hidden")
        results.add_class("-hidden")

    def _show_search_results_mode(self) -> None:
        """Show dedicated search results and hide the normal tree."""
        tree = self.query_one("#idea-list", Tree)
        results = self.query_one("#search-results", SearchResultsList)
        tree.add_class("-hidden")
        results.remove_class("-hidden")


def _normalize_suggestions(raw_values: list[str]) -> list[str]:
    """Normalize suggestion list by trimming and deduplicating in order."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        value = raw_value.strip().lower()
        if value and value not in seen:
            seen.add(value)
            normalized.append(value)
    return normalized


def _truncate_snippet(snippet: str) -> str:
    """Trim snippets to a compact single line for compatibility helpers."""
    compact = " ".join(snippet.split())
    if len(compact) <= _MAX_SNIPPET_LENGTH:
        return compact
    return f"{compact[: _MAX_SNIPPET_LENGTH - 3].rstrip()}..."


def _resolve_autocomplete_state(
    value: str,
    *,
    cursor_position: int,
    tags: tuple[str, ...],
    groups: tuple[str, ...],
    allow_empty_operator: bool,
) -> _AutocompleteState | None:
    """Resolve autocomplete state for the token around current cursor."""
    token_start, token_end = _token_bounds(value, cursor_position)
    token = value[token_start:token_end]
    context = _TokenContext(
        token=token,
        token_start=token_start,
        token_end=token_end,
        relative_cursor=max(0, min(cursor_position - token_start, len(token))),
        colon_at=token.find(":"),
    )

    value_state = _resolve_value_autocomplete_state(
        context=context,
        tags=tags,
        groups=groups,
    )
    if value_state is not None:
        return value_state

    return _resolve_operator_autocomplete_state(
        context=context,
        allow_empty_operator=allow_empty_operator,
    )


def _resolve_value_autocomplete_state(
    *,
    context: _TokenContext,
    tags: tuple[str, ...],
    groups: tuple[str, ...],
) -> _AutocompleteState | None:
    """Resolve value suggestions for `tag:` or `group:` token contexts."""
    if context.colon_at < 0 or context.relative_cursor <= context.colon_at:
        return None
    filter_field = context.token[: context.colon_at].lower()
    if filter_field not in {"tag", "group"}:
        return None
    typed_prefix = context.token[
        context.colon_at + 1 : context.relative_cursor
    ].lower()
    source = tags if filter_field == "tag" else groups
    candidates = tuple(
        candidate for candidate in source if candidate.startswith(typed_prefix)
    )
    if not candidates:
        return None
    return _AutocompleteState(
        candidates=candidates,
        replace_start=context.token_start + context.colon_at + 1,
        replace_end=context.token_end,
    )


def _resolve_operator_autocomplete_state(
    *,
    context: _TokenContext,
    allow_empty_operator: bool,
) -> _AutocompleteState | None:
    """Resolve operator suggestions (`tag:`/`group:`) for token context."""
    operator_prefix = context.token[: context.relative_cursor].lower()
    if not operator_prefix and not allow_empty_operator:
        return None
    if context.colon_at >= 0 and context.relative_cursor > 0:
        return None
    candidates = tuple(
        operator
        for operator in _SEARCH_OPERATORS
        if operator.startswith(operator_prefix)
    )
    if not candidates:
        return None
    return _AutocompleteState(
        candidates=candidates,
        replace_start=context.token_start,
        replace_end=context.token_end,
    )


def _token_bounds(value: str, cursor_position: int) -> tuple[int, int]:
    """Return start/end bounds of token around cursor, split by whitespace."""
    cursor = max(0, min(cursor_position, len(value)))
    start = cursor
    end = cursor

    while start > 0 and not value[start - 1].isspace():
        start -= 1
    while end < len(value) and not value[end].isspace():
        end += 1
    return start, end

"""Left pane: grouped idea tree with search."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from rich.text import Text
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Input, OptionList, Tree

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.events import Key
    from textual.timer import Timer
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
class _AutocompleteState:
    """Resolved autocomplete candidates and replacement target."""

    candidates: tuple[str, ...]
    replace_start: int
    replace_end: int


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


class IdeaListPanel(Vertical):
    """Left panel with search input and grouped idea tree."""

    search_query: reactive[str] = reactive("", layout=True)

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
        self._snippets_by_pk: dict[int, str] = {}
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
        yield Tree[IdeaTreeNodeData](
            "Ideas",
            data=IdeaTreeNodeData(kind="root"),
            id="idea-list",
        )

    def _reset_tree(self) -> Tree[IdeaTreeNodeData]:
        """Clear tree and internal state, returning the tree widget."""
        tree = self.query_one("#idea-list", Tree)
        tree.clear()
        self._ideas_by_pk.clear()
        self._group_nodes_by_pk.clear()
        self._idea_nodes_by_pk.clear()
        self._snippets_by_pk.clear()
        tree.root.label = "Ideas"
        tree.root.data = IdeaTreeNodeData(kind="root")
        return tree

    def load_grouped_ideas(
        self,
        grouped_ideas: list[tuple[Group, list[Idea]]],
        *,
        snippets_by_pk: dict[int, str] | None = None,
    ) -> None:
        """Replace the displayed grouped ideas."""
        tree = self._reset_tree()
        self._snippets_by_pk = dict(snippets_by_pk or {})
        first_idea_node: TreeNode[IdeaTreeNodeData] | None = None

        for group, ideas in grouped_ideas:
            group_node = tree.root.add(
                group.name,
                data=IdeaTreeNodeData(kind="group", group_pk=group.pk),
                expand=True,
            )
            self._group_nodes_by_pk[group.pk] = group_node
            for idea in ideas:
                idea_node = self._add_idea_node(
                    group_node,
                    idea,
                    group_pk=group.pk,
                    snippet=self._snippets_by_pk.get(idea.pk),
                )
                if first_idea_node is None:
                    first_idea_node = idea_node
        tree.root.expand()
        if first_idea_node is not None:
            tree.select_node(first_idea_node)
            tree.move_cursor(first_idea_node, animate=False)

    def load_grouped_search_results(
        self,
        grouped_results: list[tuple[Group, list[SearchResult]]],
    ) -> None:
        """Replace displayed ideas with ranked search results."""
        snippets_by_pk: dict[int, str] = {}
        grouped_ideas: list[tuple[Group, list[Idea]]] = []
        for group, results in grouped_results:
            ideas: list[Idea] = []
            for result in results:
                ideas.append(result.idea)
                if result.snippet:
                    snippets_by_pk[result.idea.pk] = result.snippet
            grouped_ideas.append((group, ideas))
        self.load_grouped_ideas(
            grouped_ideas,
            snippets_by_pk=snippets_by_pk,
        )

    def load_ideas(self, ideas: list[Idea]) -> None:
        """Compatibility helper to load ideas under a synthetic group."""
        tree = self._reset_tree()
        first_idea_node: TreeNode[IdeaTreeNodeData] | None = None
        for idea in ideas:
            idea_node = self._add_idea_node(
                tree.root,
                idea,
            )
            if first_idea_node is None:
                first_idea_node = idea_node
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
        snippet: str | None = None,
    ) -> TreeNode[IdeaTreeNodeData]:
        """Add an idea leaf node under parent and track it by primary key."""
        ts = _format_timestamp(idea.updated_at)
        label = Text(idea.title, style="bold")
        if ts:
            label.append(f" [{ts}]", style="dim")
        if snippet:
            label.append(f" | {_truncate_snippet(snippet)}", style="dim")
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
        tree = self.query_one("#idea-list", Tree)
        node = self._idea_nodes_by_pk.get(idea_pk)
        if node is None:
            return False
        tree.select_node(node)
        tree.move_cursor(node, animate=False)
        return True

    def get_selected_idea(self) -> Idea | None:
        """Return the currently selected idea."""
        tree = self.query_one("#idea-list", Tree)
        node = tree.cursor_node
        data = node.data if node is not None else None
        if not isinstance(data, IdeaTreeNodeData) or data.kind != "idea":
            return None
        if data.idea_pk is None:
            return None
        return self._ideas_by_pk.get(data.idea_pk)

    def get_selected_group_pk(self) -> int | None:
        """Return selected group pk when a group node is selected."""
        tree = self.query_one("#idea-list", Tree)
        node = tree.cursor_node
        data = node.data if node is not None else None
        if not isinstance(data, IdeaTreeNodeData) or data.kind != "group":
            return None
        return data.group_pk

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes with debounce."""
        if event.input.id == "search-input":
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

    def on_input_blurred(self, event: Input.Blurred) -> None:
        """Hide autocomplete when search input loses focus."""
        if event.input.id == "search-input":
            self.call_later(self._dismiss_autocomplete_if_unfocused)

    def _dismiss_autocomplete_if_unfocused(self) -> None:
        """Dismiss autocomplete unless focus moved to search/options list."""
        search = self.query_one("#search-input", Input)
        autocomplete = self.query_one("#search-autocomplete", OptionList)
        focused = self.app.focused
        if focused in {search, autocomplete}:
            return
        if focused is not None and autocomplete in focused.ancestors:
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

    def _fire_search(self, query: str) -> None:
        """Post the debounced search message."""
        self.post_message(self.SearchChanged(query))

    def on_tree_node_selected(
        self,
        event: Tree.NodeSelected[IdeaTreeNodeData],
    ) -> None:
        """Handle idea selection from tree."""
        self._post_if_idea_node(event.node.data)

    def on_tree_node_highlighted(
        self,
        event: Tree.NodeHighlighted[IdeaTreeNodeData],
    ) -> None:
        """Handle highlight change in tree."""
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

    def clear_search(self) -> None:
        """Clear the search input."""
        search = self.query_one("#search-input", Input)
        search.value = ""
        self.dismiss_autocomplete()
        search.focus()

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
        """Handle autocomplete keys while search input is focused."""
        search = self.query_one("#search-input", Input)
        if self.app.focused is not search:
            return

        if event.key == "tab":
            event.prevent_default()
            event.stop()
            if self._autocomplete_is_visible():
                self._cycle_autocomplete(1)
            else:
                self._sync_autocomplete(allow_empty_operator=True)
            return

        if event.key in {"shift+tab", "backtab"}:
            event.prevent_default()
            event.stop()
            if self._autocomplete_is_visible():
                self._cycle_autocomplete(-1)
            else:
                self._sync_autocomplete(allow_empty_operator=True)
            return

        if event.key == "down" and self._autocomplete_is_visible():
            event.prevent_default()
            event.stop()
            self._cycle_autocomplete(1)
            return

        if event.key == "up" and self._autocomplete_is_visible():
            event.prevent_default()
            event.stop()
            self._cycle_autocomplete(-1)
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

    def dismiss_autocomplete(self) -> bool:
        """Close autocomplete popup if it is currently visible."""
        autocomplete = self.query_one("#search-autocomplete", OptionList)
        if not self._autocomplete_is_visible():
            return False
        autocomplete.add_class("-hidden")
        autocomplete.clear_options()
        self._autocomplete_state = None
        return True

    def _autocomplete_is_visible(self) -> bool:
        """Return whether autocomplete popup is currently visible."""
        autocomplete = self.query_one("#search-autocomplete", OptionList)
        return not autocomplete.has_class("-hidden")

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
        autocomplete.set_options(state.candidates)
        autocomplete.highlighted = 0
        autocomplete.remove_class("-hidden")

    def _cycle_autocomplete(self, direction: Literal[-1, 1]) -> None:
        """Move autocomplete highlight forward or backward with wrapping."""
        autocomplete = self.query_one("#search-autocomplete", OptionList)
        count = autocomplete.option_count
        if count == 0:
            return
        highlighted = autocomplete.highlighted
        if highlighted is None:
            autocomplete.highlighted = 0
            return
        autocomplete.highlighted = (highlighted + direction) % count

    def _apply_highlighted_autocomplete(self) -> None:
        """Apply the currently highlighted autocomplete candidate."""
        state = self._autocomplete_state
        if state is None:
            return
        autocomplete = self.query_one("#search-autocomplete", OptionList)
        highlighted = autocomplete.highlighted
        if highlighted is None:
            return
        if highlighted >= len(state.candidates):
            return
        suggestion = state.candidates[highlighted]

        search = self.query_one("#search-input", Input)
        before = search.value[: state.replace_start]
        after = search.value[state.replace_end :]
        # Matches on_input_changed assumption: one sync Input.Changed event.
        self._suspend_autocomplete_sync = True
        search.value = f"{before}{suggestion}{after}"
        search.cursor_position = state.replace_start + len(suggestion)
        self.dismiss_autocomplete()


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
    """Trim snippets to a compact single line for the tree."""
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

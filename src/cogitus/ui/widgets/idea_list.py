"""Left pane: grouped idea tree with search."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from rich.text import Text
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Input, Tree

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.timer import Timer
    from textual.widgets.tree import TreeNode

    from cogitus.models.group import Group
    from cogitus.models.idea import Idea

_DAYS_IN_WEEK = 7


@dataclass(frozen=True)
class IdeaTreeNodeData:
    """Typed metadata for tree nodes."""

    kind: Literal["root", "group", "idea"]
    group_pk: int | None = None
    idea_pk: int | None = None


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

    def compose(self) -> ComposeResult:
        """Compose the idea list panel."""
        yield Input(
            placeholder="Search ideas... (/ to focus)",
            id="search-input",
        )
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
        tree.root.label = "Ideas"
        tree.root.data = IdeaTreeNodeData(kind="root")
        return tree

    def load_grouped_ideas(
        self,
        grouped_ideas: list[tuple[Group, list[Idea]]],
    ) -> None:
        """Replace the displayed grouped ideas."""
        tree = self._reset_tree()
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
                )
                if first_idea_node is None:
                    first_idea_node = idea_node
        tree.root.expand()
        if first_idea_node is not None:
            tree.select_node(first_idea_node)
            tree.move_cursor(first_idea_node, animate=False)

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
    ) -> TreeNode[IdeaTreeNodeData]:
        """Add an idea leaf node under parent and track it by primary key."""
        ts = _format_timestamp(idea.updated_at)
        label = Text(idea.title, style="bold")
        if ts:
            label.append(f" [{ts}]", style="dim")
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
            if self._debounce_timer is not None:
                self._debounce_timer.stop()
            self._debounce_timer = self.set_timer(
                0.2,
                lambda: self._fire_search(event.value),
            )

    def _fire_search(self, query: str) -> None:
        """Post the debounced search message."""
        self.post_message(self.SearchChanged(query))

    def on_tree_node_selected(
        self,
        event: Tree.NodeSelected[IdeaTreeNodeData],
    ) -> None:
        """Handle idea selection from tree."""
        data = event.node.data
        if (
            data is not None
            and data.kind == "idea"
            and data.idea_pk is not None
            and data.idea_pk in self._ideas_by_pk
        ):
            self.post_message(
                self.IdeaSelected(self._ideas_by_pk[data.idea_pk])
            )

    def on_tree_node_highlighted(
        self,
        event: Tree.NodeHighlighted[IdeaTreeNodeData],
    ) -> None:
        """Handle highlight change in tree."""
        data = event.node.data if event.node is not None else None
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
        search.focus()

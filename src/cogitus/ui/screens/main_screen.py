"""Main application screen with two-pane layout."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding, BindingType
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, ListView

from cogitus.ui.clipboard import copy_to_clipboard
from cogitus.ui.screens.idea_form_screen import (
    ConfirmDialog,
    HelpScreen,
    IdeaFormScreen,
)
from cogitus.ui.widgets.idea_list import IdeaListPanel
from cogitus.ui.widgets.idea_view import IdeaView

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.app import ComposeResult

    from cogitus.services.idea_service import IdeaService


class MainScreen(Screen[None]):
    """Two-pane main screen: idea list + detail view."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("n", "new_idea", "New", key_display="N"),
        Binding("e", "edit_idea", "Edit", key_display="E"),
        Binding("d", "delete_idea", "Delete", key_display="D"),
        Binding("slash", "focus_search", "Search", key_display="/"),
        Binding("escape", "cancel_search", "Back", show=False),
        Binding(
            "question_mark",
            "show_help",
            "Help",
            key_display="?",
        ),
        Binding(
            "tab",
            "toggle_focus",
            "Switch Pane",
            show=False,
        ),
        Binding(
            "ctrl+b",
            "toggle_list_panel",
            "Toggle List",
            key_display="Ctrl+B",
        ),
        Binding(
            "y",
            "copy_idea_body",
            "Copy body",
            key_display="Y",
        ),
        Binding("q", "quit_app", "Quit", key_display="Q"),
    ]

    def __init__(
        self,
        service: IdeaService,
        *,
        initial_select_pk: int | None = None,
        on_selected_idea_changed: Callable[[int | None], None] | None = None,
    ) -> None:
        """Initialize with the idea service.

        Args:
            service: The IdeaService instance.
            initial_select_pk: Idea primary key to select on first load.
            on_selected_idea_changed: Callback for selected idea changes.
        """
        super().__init__()
        self._service = service
        self._initial_select_pk = initial_select_pk
        self._on_selected_idea_changed = on_selected_idea_changed
        self._selected_idea_pk: int | None = None
        self._active_pane: str = "list"
        self._focus_before_search: str = "list"

    def compose(self) -> ComposeResult:
        """Compose the main screen layout."""
        yield Header()
        yield IdeaListPanel(id="idea-list-panel")
        yield IdeaView(id="content-panel")
        yield Footer()

    def on_mount(self) -> None:
        """Load ideas when screen mounts."""
        self.refresh_ideas(select_pk=self._initial_select_pk)
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        panel.query_one("#idea-list", ListView).focus()

    def refresh_ideas(self, select_pk: int | None = None) -> None:
        """Reload the idea list from the service."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        ideas = self._service.list_ideas()
        panel.load_ideas(ideas)

        view = self.query_one("#content-panel", IdeaView)
        if ideas:
            if select_pk is not None:
                for i, idea in enumerate(ideas):
                    if idea.pk == select_pk:
                        lv = panel.query_one("#idea-list", ListView)
                        lv.index = i
                        break
            selected = panel.get_selected_idea()
            if selected is not None:
                self._set_selected_idea(selected.pk)
                view.show_idea(selected)
            else:
                self._set_selected_idea(None)
                view.show_empty()
        else:
            self._set_selected_idea(None)
            view.show_empty()

    def on_idea_list_panel_idea_selected(
        self, event: IdeaListPanel.IdeaSelected
    ) -> None:
        """Update detail view when an idea is selected."""
        view = self.query_one("#content-panel", IdeaView)
        fresh = self._service.get_idea(event.idea.pk)
        if fresh is not None:
            self._set_selected_idea(fresh.pk)
            view.show_idea(fresh)
        else:
            self._set_selected_idea(None)
            view.show_empty()

    def on_idea_list_panel_search_changed(
        self, event: IdeaListPanel.SearchChanged
    ) -> None:
        """Filter ideas based on search query."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        if event.query.strip():
            ideas = self._service.search_ideas(event.query)
        else:
            ideas = self._service.list_ideas()
        panel.load_ideas(ideas)
        view = self.query_one("#content-panel", IdeaView)
        selected = panel.get_selected_idea()
        if selected is not None:
            self._set_selected_idea(selected.pk)
            view.show_idea(selected)
        else:
            self._set_selected_idea(None)
            view.show_empty()

    def action_new_idea(self) -> None:
        """Open the new idea form."""
        self.app.push_screen(
            IdeaFormScreen(self._service),
            callback=self._on_form_dismiss,
        )

    def action_edit_idea(self) -> None:
        """Open the edit form for the selected idea."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        idea = panel.get_selected_idea()
        if idea is None:
            self.notify("No idea selected", severity="warning")
            return
        fresh = self._service.get_idea(idea.pk)
        if fresh is None:
            self.notify("Idea not found", severity="error")
            return
        self.app.push_screen(
            IdeaFormScreen(self._service, idea=fresh),
            callback=self._on_form_dismiss,
        )

    def action_delete_idea(self) -> None:
        """Delete the selected idea with confirmation."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        idea = panel.get_selected_idea()
        if idea is None:
            self.notify("No idea selected", severity="warning")
            return
        self.app.push_screen(
            ConfirmDialog(f'Delete "{idea.title}"?'),
            callback=lambda confirmed: self._on_delete_confirm(
                idea.pk, confirmed=confirmed
            ),
        )

    def action_copy_idea_body(self) -> None:
        """Copy the selected idea's body to the system clipboard."""
        if self._selected_idea_pk is None:
            self.notify("No idea selected", severity="warning")
            return
        idea = self._service.get_idea(self._selected_idea_pk)
        if idea is None:
            self.notify("Idea not found", severity="error")
            return
        if not idea.body:
            self.notify("Idea has no body to copy", severity="warning")
            return
        if copy_to_clipboard(idea.body, self.app):
            self.notify("Copied idea body to clipboard")
        else:
            self.notify("Clipboard unavailable", severity="warning")

    def _on_delete_confirm(
        self,
        pk: int,
        *,
        confirmed: bool,
    ) -> None:
        """Handle delete confirmation result."""
        if confirmed:
            self._service.delete_idea(pk)
            self.notify("Idea deleted")
            self.refresh_ideas()

    def _on_form_dismiss(self, result: int | None) -> None:
        """Handle form dismiss — result is the idea pk."""
        if result is not None:
            self.refresh_ideas(select_pk=result)

    def action_focus_search(self) -> None:
        """Focus the search input."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        if self.app.focused is not search:
            self._focus_before_search = self._active_pane
        search.focus()

    def action_cancel_search(self) -> None:
        """Clear search and return focus to the previous panel."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        if self.app.focused is not search:
            return

        search.value = ""
        if self._focus_before_search == "content":
            self.query_one("#content-panel", IdeaView).focus()
            self._active_pane = "content"
        else:
            panel.query_one("#idea-list", ListView).focus()
            self._active_pane = "list"

    def action_show_help(self) -> None:
        """Show the help overlay."""
        self.app.push_screen(HelpScreen())

    def action_toggle_focus(self) -> None:
        """Toggle focus between list and content panes."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        if panel.has_focus_within:
            content = self.query_one("#content-panel", IdeaView)
            content.focus()
            self._active_pane = "content"
        else:
            list_view = panel.query_one("#idea-list")
            list_view.focus()
            self._active_pane = "list"

    def action_toggle_list_panel(self) -> None:
        """Collapse/expand the left list panel."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        content = self.query_one("#content-panel", IdeaView)
        if panel.has_class("collapsed"):
            panel.remove_class("collapsed")
            panel.query_one("#idea-list", ListView).focus()
            self._active_pane = "list"
        else:
            panel.add_class("collapsed")
            content.focus()
            self._active_pane = "content"

    def action_quit_app(self) -> None:
        """Quit the application."""
        self.app.exit()

    def _set_selected_idea(self, idea_pk: int | None) -> None:
        """Track and publish the selected idea primary key."""
        self._selected_idea_pk = idea_pk
        if self._on_selected_idea_changed is not None:
            self._on_selected_idea_changed(idea_pk)

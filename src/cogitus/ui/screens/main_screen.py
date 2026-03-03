"""Main application screen with two-pane layout."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, ClassVar

from textual.binding import ActiveBinding, Binding, BindingType
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Markdown

from cogitus.config import (
    DEFAULT_EDIT_BODY_CURSOR_MODE,
    DEFAULT_NEW_IDEA_GROUP_MODE,
    EditBodyCursorMode,
    NewIdeaGroupMode,
)
from cogitus.search import parse_search_query
from cogitus.ui.clipboard import copy_to_clipboard
from cogitus.ui.screens.idea_form_screen import (
    ConfirmDialog,
    GroupDeleteReassignScreen,
    GroupFormScreen,
    HelpScreen,
    IdeaFormScreen,
)
from cogitus.ui.widgets.idea_list import IdeaListPanel
from cogitus.ui.widgets.idea_view import IdeaView
from cogitus.ui.widgets.search_results import SearchResultsList

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.app import ComposeResult

    from cogitus.models.group import Group
    from cogitus.services.idea_service import IdeaService


class MainScreen(Screen[None]):
    """Two-pane main screen: idea list + detail view."""

    _SEARCH_MODE_DISABLED_ACTIONS: ClassVar[frozenset[str]] = frozenset(
        {
            "new_idea",
            "new_group",
            "delete_group",
            "delete_idea",
        }
    )
    _SEARCH_INPUT_DISABLED_ACTIONS: ClassVar[frozenset[str]] = frozenset(
        {
            "edit_idea",
            "copy_idea_body",
        }
    )
    _SEARCH_INPUT_FOOTER_ACTIONS: ClassVar[frozenset[str]] = frozenset(
        {
            "footer_search_results",
            "footer_exit_search",
        }
    )
    _SEARCH_RESULTS_FOOTER_ACTIONS: ClassVar[frozenset[str]] = frozenset(
        {
            "footer_next_result",
            "footer_previous_result",
            "footer_back_to_search",
        }
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("n", "new_idea", "New", key_display="n"),
        Binding("g", "new_group", "New Group", key_display="g"),
        Binding(
            "G",
            "delete_group",
            "Delete Group",
            key_display="G",
        ),
        Binding("e", "edit_idea", "Edit", key_display="e"),
        Binding("d", "delete_idea", "Delete", key_display="d"),
        Binding("slash", "focus_search", "Search", key_display="/"),
        Binding("escape", "cancel_search", "Back", show=False),
        Binding(
            "down",
            "footer_search_results",
            "Results",
            show=True,
            key_display="Down",
            priority=True,
        ),
        Binding(
            "escape",
            "footer_exit_search",
            "Exit Search",
            show=True,
            key_display="Esc",
            priority=True,
        ),
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
            key_display="ctrl+b",
        ),
        Binding(
            "y",
            "copy_idea_body",
            "Copy body",
            key_display="y",
        ),
        Binding("q", "quit_app", "Quit", key_display="q"),
    ]

    def __init__(
        self,
        service: IdeaService,
        *,
        initial_select_pk: int | None = None,
        on_selected_idea_changed: Callable[[int | None], None] | None = None,
        edit_body_cursor_mode: EditBodyCursorMode = (
            DEFAULT_EDIT_BODY_CURSOR_MODE
        ),
        new_idea_group_mode: NewIdeaGroupMode = (DEFAULT_NEW_IDEA_GROUP_MODE),
    ) -> None:
        """Initialize with the idea service.

        Args:
            service: The IdeaService instance.
            initial_select_pk: Idea primary key to select on first load.
            on_selected_idea_changed: Callback for selected idea changes.
            edit_body_cursor_mode: Edit form body cursor mode.
            new_idea_group_mode: New idea group selection mode.
        """
        super().__init__()
        self._service = service
        self._initial_select_pk = initial_select_pk
        self._on_selected_idea_changed = on_selected_idea_changed
        self._edit_body_cursor_mode = edit_body_cursor_mode
        self._new_idea_group_mode = new_idea_group_mode
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
        panel.browse_widget().focus()

    def refresh_ideas(self, select_pk: int | None = None) -> None:
        """Reload the idea list from the service."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        panel.set_autocomplete_sources(
            tags=[tag.name for tag in self._service.list_tags_in_use()],
            groups=[group.name for group in self._service.list_groups()],
        )
        search_query = panel.query_one("#search-input", Input).value.strip()
        if search_query:
            self._refresh_search_results(
                panel,
                search_query=search_query,
                select_pk=select_pk,
            )
            return

        view = self.query_one("#content-panel", IdeaView)
        grouped_ideas = self._service.list_ideas_grouped(None)
        panel.load_grouped_ideas(grouped_ideas)
        has_ideas = any(group_ideas for _, group_ideas in grouped_ideas)
        if has_ideas:
            if select_pk is not None:
                panel.select_idea(select_pk)
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

    def _refresh_search_results(
        self,
        panel: IdeaListPanel,
        *,
        search_query: str,
        select_pk: int | None,
    ) -> None:
        """Refresh the active search view without clobbering preview state."""
        parsed = parse_search_query(search_query)
        search_results = self._service.search_results(search_query)
        panel.load_search_results(
            search_results,
            show_match_rows=parsed.text is not None,
        )
        if select_pk is not None:
            panel.select_idea(select_pk)
        self._show_search_selection_preview(
            panel,
            commit_selection=(
                select_pk is not None
                or self.app.focused
                is panel.query_one("#search-results", SearchResultsList)
            ),
        )

    def _show_search_selection_preview(
        self,
        panel: IdeaListPanel,
        *,
        commit_selection: bool,
    ) -> None:
        """Show the current search preview and optionally commit it."""
        view = self.query_one("#content-panel", IdeaView)
        selected = panel.get_selected_idea()
        if selected is not None:
            if commit_selection:
                self._set_selected_idea(selected.pk)
            view.show_idea(selected)
            return
        if commit_selection:
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
        view = self.query_one("#content-panel", IdeaView)
        query = event.query.strip()
        if query:
            parsed = parse_search_query(query)
            panel.load_search_results(
                self._service.search_results(query),
                show_match_rows=parsed.text is not None,
            )
            selected = panel.get_selected_idea()
            if selected is not None:
                view.show_idea(selected)
            else:
                view.show_empty()
            return

        grouped_ideas = self._service.list_ideas_grouped(None)
        panel.load_grouped_ideas(grouped_ideas)
        if self._selected_idea_pk is not None:
            panel.select_idea(self._selected_idea_pk)
        selected = panel.get_selected_idea()
        if selected is not None:
            self._set_selected_idea(selected.pk)
            view.show_idea(selected)
        else:
            self._set_selected_idea(None)
            view.show_empty()

    def action_new_idea(self) -> None:
        """Open the new idea form."""
        initial_group_pk = None
        if self._new_idea_group_mode == NewIdeaGroupMode.CONTEXTUAL:
            initial_group_pk = self._get_contextual_new_idea_group_pk()
        self.app.push_screen(
            IdeaFormScreen(
                self._service,
                initial_group_pk=initial_group_pk,
                edit_body_cursor_mode=self._edit_body_cursor_mode,
            ),
            callback=self._on_form_dismiss,
        )

    def _get_contextual_new_idea_group_pk(self) -> int | None:
        """Return current group context from the left idea tree selection."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        selected_group_pk = panel.get_selected_group_pk()
        if selected_group_pk is not None:
            return selected_group_pk

        selected_idea = panel.get_selected_idea()
        if selected_idea is None:
            return None
        return selected_idea.group.pk

    def action_new_group(self) -> None:
        """Open the new group form."""
        self.app.push_screen(
            GroupFormScreen(self._service),
            callback=self._on_group_form_dismiss,
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
            IdeaFormScreen(
                self._service,
                idea=fresh,
                edit_body_cursor_mode=self._edit_body_cursor_mode,
            ),
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

    def action_delete_group(self) -> None:
        """Delete selected group with optional bulk move."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        group_pk = panel.get_selected_group_pk()
        if group_pk is None:
            self.notify("No group selected", severity="warning")
            return

        groups = self._service.list_groups()
        group = next((item for item in groups if item.pk == group_pk), None)
        if group is None:
            self.notify("Group not found", severity="error")
            return
        if group.name == self._service.default_group_name:
            self.notify("Default group cannot be deleted", severity="warning")
            return

        self._show_delete_group_flow(group_pk, group.name, groups)

    def _show_delete_group_flow(
        self,
        group_pk: int,
        group_name: str,
        groups: list[Group],
    ) -> None:
        """Open confirm or reassignment dialog for group deletion."""
        if not self._service.has_ideas_in_group(group_pk):
            self.app.push_screen(
                ConfirmDialog(f'Delete group "{group_name}"?'),
                callback=lambda confirmed: self._on_delete_group_confirm(
                    group_pk,
                    confirmed=confirmed,
                ),
            )
            return

        options = [
            (item.name, item.pk) for item in groups if item.pk != group_pk
        ]
        self.app.push_screen(
            GroupDeleteReassignScreen(group_name, options),
            callback=lambda target_pk: self._on_delete_group_reassign(
                group_pk,
                target_pk,
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

        selected_text = self._get_selected_rendered_body_text()
        text_to_copy = selected_text if selected_text is not None else idea.body
        if copy_to_clipboard(text_to_copy, self.app):
            if selected_text is not None:
                self.notify("Copied selection to clipboard")
            else:
                self.notify("Copied idea body to clipboard")
        else:
            self.notify("Clipboard unavailable", severity="warning")

    def _get_selected_rendered_body_text(self) -> str | None:
        """Return selected text in rendered body, if any."""
        selected_text = self.get_selected_text()
        if selected_text:
            return selected_text

        view = self.query_one("#content-panel", IdeaView)
        body = view.query_one("#idea-view-body", Markdown)
        selection = body.text_selection
        if selection is None:
            return None

        selected = body.get_selection(selection)
        if selected is None:
            return None
        widget_text, _ = selected
        return widget_text or None

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

    def _on_group_form_dismiss(self, result: int | None) -> None:
        """Refresh tree after group create."""
        if result is not None:
            self.notify("Group created")
            self.refresh_ideas()

    def _on_delete_group_confirm(
        self,
        group_pk: int,
        *,
        confirmed: bool,
    ) -> None:
        """Handle delete-group confirmation for empty groups."""
        if confirmed:
            try:
                self._service.delete_group(group_pk)
            except ValueError as exc:
                self.notify(str(exc), severity="error")
                return
            self.notify("Group deleted")
            self.refresh_ideas()

    def _on_delete_group_reassign(
        self,
        group_pk: int,
        target_group_pk: int | None,
    ) -> None:
        """Handle group delete with reassignment."""
        if target_group_pk is None:
            return
        try:
            self._service.delete_group(
                group_pk,
                move_to_group_pk=target_group_pk,
            )
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        self.notify("Group deleted and ideas moved")
        self.refresh_ideas()

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
        if panel.dismiss_autocomplete():
            return
        search = panel.query_one("#search-input", Input)
        results = panel.query_one("#search-results", SearchResultsList)
        if self.app.focused is results and panel.search_is_active():
            search.focus()
            return

        if self.app.focused is not search:
            return

        search.value = ""
        if self._focus_before_search == "content":
            self.query_one("#content-panel", IdeaView).focus()
            self._active_pane = "content"
        else:
            panel.focus_preferred_list_widget()
            self._active_pane = "list"

    def action_show_help(self) -> None:
        """Show the help overlay."""
        self.app.push_screen(HelpScreen())

    def action_toggle_focus(self) -> None:
        """Toggle focus between list and content panes."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        if self.app.focused is panel.query_one("#search-input", Input):
            return
        if panel.has_focus_within:
            content = self.query_one("#content-panel", IdeaView)
            content.focus()
            self._active_pane = "content"
        else:
            panel.focus_preferred_list_widget()
            self._active_pane = "list"

    def action_toggle_list_panel(self) -> None:
        """Collapse/expand the left list panel."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        content = self.query_one("#content-panel", IdeaView)
        if panel.has_class("collapsed"):
            panel.remove_class("collapsed")
            panel.focus_preferred_list_widget()
            self._active_pane = "list"
        else:
            panel.add_class("collapsed")
            content.focus()
            self._active_pane = "content"

    def action_quit_app(self) -> None:
        """Quit the application."""
        self.app.exit()

    def check_action(
        self,
        action: str,
        parameters: tuple[object, ...],
    ) -> bool | None:
        """Show search-mode footer hints only when they are relevant."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        results = panel.query_one("#search-results", SearchResultsList)

        if panel.search_is_active():
            if (
                self.app.focused in {search, results}
                and action in self._SEARCH_MODE_DISABLED_ACTIONS
            ):
                return False
            if (
                self.app.focused is search
                and action in self._SEARCH_INPUT_DISABLED_ACTIONS
            ):
                return False

        if action == "footer_search_results":
            return (
                self.app.focused is search
                and panel.search_is_active()
                and not panel.autocomplete_is_visible()
                and bool(panel.get_selected_idea())
            )
        if action == "footer_exit_search":
            return self.app.focused is search and panel.search_is_active()
        return super().check_action(action, parameters)

    @property
    def active_bindings(self) -> dict[str, ActiveBinding]:
        """Return bindings with search-mode footer filtering."""
        bindings = super().active_bindings
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        search = panel.query_one("#search-input", Input)
        results = panel.query_one("#search-results", SearchResultsList)

        if self.app.focused is search and panel.search_is_active():
            bindings = {
                key: binding
                for key, binding in bindings.items()
                if binding.binding.action in self._SEARCH_INPUT_FOOTER_ACTIONS
            }
        elif self.app.focused is results and panel.search_is_active():
            bindings = {
                key: binding
                for key, binding in bindings.items()
                if binding.binding.action in self._SEARCH_RESULTS_FOOTER_ACTIONS
            }

        up_binding = bindings.get("up")
        if (
            self.app.focused is results
            and panel.search_is_active()
            and up_binding is not None
            and up_binding.binding.action == "footer_previous_result"
        ):
            description = (
                "Search" if panel.is_first_result_selected() else "Prev Result"
            )
            bindings["up"] = ActiveBinding(
                up_binding.node,
                replace(up_binding.binding, description=description),
                up_binding.enabled,
                up_binding.tooltip,
            )
        return bindings

    def _set_selected_idea(self, idea_pk: int | None) -> None:
        """Track and publish the selected idea primary key."""
        self._selected_idea_pk = idea_pk
        if self._on_selected_idea_changed is not None:
            self._on_selected_idea_changed(idea_pk)

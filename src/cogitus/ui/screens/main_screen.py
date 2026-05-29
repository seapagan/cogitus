"""Main application screen with two-pane layout."""

from __future__ import annotations

from dataclasses import replace
from shlex import quote as shlex_quote
from typing import TYPE_CHECKING, ClassVar

from textual import work
from textual.binding import ActiveBinding, Binding, BindingType
from textual.screen import Screen
from textual.widgets import Header
from textual.worker import Worker, WorkerState

from cogitus.backends import BackendConfig
from cogitus.backends.protocols import SyncingIdeaBackend
from cogitus.backends.types import RemoteSyncResult
from cogitus.config import (
    DEFAULT_EDIT_BODY_CURSOR_MODE,
    DEFAULT_NEW_IDEA_GROUP_MODE,
    DataBackendMode,
    EditBodyCursorMode,
    NewIdeaGroupMode,
)
from cogitus.metadata import AppMetadata, get_app_metadata
from cogitus.search import parse_search_query
from cogitus.ui.clipboard import copy_to_clipboard
from cogitus.ui.screens.idea_form_screen import (
    AboutScreen,
    BackendConfigScreen,
    ConfirmDialog,
    GroupDeleteReassignScreen,
    GroupFormScreen,
    HelpScreen,
    IdeaFormScreen,
    NameInputScreen,
    RemoteCloneModeAction,
    RemoteCloneProgressScreen,
    RemoteCloneSwitchModeScreen,
    RemoteStartupRecoveryAction,
    RemoteStartupRecoveryScreen,
)
from cogitus.ui.widgets.footer import CogitusStatusBar
from cogitus.ui.widgets.idea_list import IdeaListPanel
from cogitus.ui.widgets.idea_view import IdeaView

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.app import ComposeResult
    from textual.events import AppFocus, ScreenResume
    from textual.timer import Timer

    from cogitus.backends.protocols import IdeaBackend
    from cogitus.models.group import Group
    from cogitus.models.idea import Idea
    from cogitus.repositories.snapshot_import_repo import (
        SnapshotImportProgress,
    )


class MainScreen(Screen[None]):
    """Two-pane main screen: idea list + detail view."""

    REMOTE_SYNC_INTERVAL_SECONDS: ClassVar[int] = 60

    _SEARCH_MODE_DISABLED_ACTIONS: ClassVar[frozenset[str]] = frozenset(
        {
            "new_idea",
            "new_group",
            "new_subgroup",
            "delete_group",
            "delete_idea",
        }
    )
    _SEARCH_INPUT_DISABLED_ACTIONS: ClassVar[frozenset[str]] = frozenset(
        {
            "edit_idea",
            "rename_selected",
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
    _REMOTE_READ_ONLY_ACTIONS: ClassVar[frozenset[str]] = frozenset(
        {
            "new_idea",
            "new_group",
            "new_subgroup",
            "delete_group",
            "edit_idea",
            "rename_selected",
            "delete_idea",
        }
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("n", "new_idea", "New", key_display="n"),
        Binding("g", "new_group", "New Group", key_display="g"),
        Binding(
            "ctrl+g",
            "new_subgroup",
            "New Subgroup",
            key_display="ctrl+g",
        ),
        Binding(
            "G",
            "delete_group",
            "Delete Group",
            key_display="G",
        ),
        Binding("e", "edit_idea", "Edit", key_display="e"),
        Binding("r", "rename_selected", "Rename", key_display="r"),
        Binding("d", "delete_idea", "Delete", key_display="d"),
        Binding("c", "show_backend_config", "Settings", show=False),
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
            "a",
            "show_about",
            "About",
            key_display="a",
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
            show=True,
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
        service: IdeaBackend,
        *,
        initial_select_pk: int | None = None,
        on_selected_idea_changed: Callable[[int | None], None] | None = None,
        edit_body_cursor_mode: EditBodyCursorMode = (
            DEFAULT_EDIT_BODY_CURSOR_MODE
        ),
        new_idea_group_mode: NewIdeaGroupMode = (DEFAULT_NEW_IDEA_GROUP_MODE),
        app_metadata: AppMetadata | None = None,
    ) -> None:
        """Initialize with the idea service.

        Args:
            service: The idea backend instance.
            initial_select_pk: Idea primary key to select on first load.
            on_selected_idea_changed: Callback for selected idea changes.
            edit_body_cursor_mode: Edit form body cursor mode.
            new_idea_group_mode: New idea group selection mode.
            app_metadata: App metadata shown in the top bar.
        """
        super().__init__()
        resolved_app_metadata = (
            get_app_metadata() if app_metadata is None else app_metadata
        )
        self._app_metadata = resolved_app_metadata
        self._service = service
        self._initial_select_pk = initial_select_pk
        self._on_selected_idea_changed = on_selected_idea_changed
        self._edit_body_cursor_mode = edit_body_cursor_mode
        self._new_idea_group_mode = new_idea_group_mode
        self._preserve_idea_scroll_position = True
        self._app_title = resolved_app_metadata.title
        self._app_version = resolved_app_metadata.version
        self.title = self._app_title
        self._selected_idea_pk: int | None = None
        self._active_pane: str = "list"
        self._focus_before_search: str = "list"
        self._remote_sync_timer: Timer | None = None
        self._remote_sync_worker: Worker[RemoteSyncResult] | None = None
        self._remote_clone_worker: Worker[None] | None = None
        self._remote_sync_error: str | None = None
        self._initial_remote_sync_pending = False
        self._remote_startup_modal_open = False
        self._remote_cached_read_only = False
        self._pending_pre_edit_action: Callable[[], None] | None = None
        self._remote_clone_progress_screen: RemoteCloneProgressScreen | None = (
            None
        )
        self._clone_started_in_remote_mode = False
        self._base_sub_title = ""

    def compose(self) -> ComposeResult:
        """Compose the main screen layout."""
        yield Header(icon=f"v{self._app_version}")
        yield IdeaListPanel(id="idea-list-panel")
        yield IdeaView(id="content-panel")
        yield CogitusStatusBar()

    def on_mount(self) -> None:
        """Load ideas when screen mounts."""
        self._preserve_idea_scroll_position = bool(
            getattr(self.app, "_preserve_idea_scroll_position", True)
        )
        self._base_sub_title = self.app.sub_title
        self.refresh_ideas(select_pk=self._initial_select_pk)
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        panel.browse_widget().focus()
        self._configure_remote_sync()

    def on_app_focus(self, _event: AppFocus) -> None:
        """Refresh visible relative timestamps when the app regains focus."""
        self._refresh_relative_timestamps()

    def on_screen_resume(self, _event: ScreenResume) -> None:
        """Refresh visible relative timestamps when this screen resumes."""
        self._refresh_relative_timestamps()

    def flush_idea_scroll_position(self) -> None:
        """Persist the currently displayed idea scroll position."""
        if not self.is_mounted:
            return
        self._save_current_idea_scroll(
            self.query_one("#content-panel", IdeaView)
        )

    def replace_service(self, service: IdeaBackend) -> None:
        """Swap in a new backend and refresh the visible state."""
        self._service = service
        self._configure_remote_sync()
        self.refresh_ideas(select_pk=self._selected_idea_pk)

    def _configure_remote_sync(self) -> None:
        """Enable or disable background sync based on backend support."""
        if self._remote_sync_timer is not None:
            self._remote_sync_timer.stop()
            self._remote_sync_timer = None
        self._remote_sync_worker = None
        self._remote_sync_error = None
        self._initial_remote_sync_pending = False
        self._remote_startup_modal_open = False
        self._pending_pre_edit_action = None
        self._remote_clone_progress_screen = None
        self._clone_started_in_remote_mode = False
        self._clear_sync_indicator()
        if not self._syncing_backend():
            self._set_remote_cached_read_only(read_only=False)
            return
        self._initial_remote_sync_pending = True
        self._request_remote_sync()
        self._remote_sync_timer = self.set_interval(
            self.REMOTE_SYNC_INTERVAL_SECONDS,
            self._request_remote_sync,
        )

    def _set_remote_cached_read_only(self, *, read_only: bool) -> None:
        """Update cached-mode mutability and the footer warning marker."""
        self._remote_cached_read_only = read_only
        if not self.is_mounted:
            return
        self.query_one(CogitusStatusBar).show_cache_warning = read_only
        self.refresh_bindings()

    def _syncing_backend(self) -> SyncingIdeaBackend | None:
        """Return the backend when it supports remote sync."""
        if isinstance(self._service, SyncingIdeaBackend):
            return self._service
        return None

    def _request_remote_sync(self) -> None:
        """Schedule a background sync when the remote backend is active."""
        if self.app.screen is not self:
            return
        if self._syncing_backend() is None:
            return
        if self._remote_startup_modal_open:
            return
        if self._remote_sync_in_progress():
            return
        self._remote_sync_worker = self._run_remote_sync()

    def _remote_sync_in_progress(self) -> bool:
        """Return whether a background remote sync is still running."""
        worker = self._remote_sync_worker
        return worker is not None and not worker.is_finished

    @work(thread=True, exclusive=True, exit_on_error=False)
    def _run_remote_sync(self) -> RemoteSyncResult:
        """Refresh the remote cache without blocking the UI."""
        backend = self._syncing_backend()
        if backend is None:
            return RemoteSyncResult(changed=False)
        return backend.sync_from_remote()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Refresh the UI when a background remote sync completes."""
        if event.worker is self._remote_clone_worker:
            if event.state == WorkerState.SUCCESS:
                self._handle_remote_clone_success()
                return
            if event.state == WorkerState.ERROR:
                self._handle_remote_clone_error(event.worker)
                return
        if event.worker is not self._remote_sync_worker:
            return
        if event.state == WorkerState.SUCCESS:
            self._handle_remote_sync_success()
            result = event.worker.result
            if not isinstance(result, RemoteSyncResult) or result.changed:
                self._refresh_after_remote_sync()
            self._run_pending_pre_edit_action()
            return
        if event.state == WorkerState.ERROR:
            self._pending_pre_edit_action = None
            self._handle_remote_sync_error(event.worker)

    def _handle_remote_sync_success(self) -> None:
        """Apply UI state updates after a successful remote sync."""
        was_read_only = self._remote_cached_read_only
        self._initial_remote_sync_pending = False
        self._remote_sync_error = None
        self._clear_sync_indicator()
        if not was_read_only:
            return
        self._set_remote_cached_read_only(read_only=False)
        restore_remote_mode = getattr(
            self.app,
            "restore_remote_mode",
            None,
        )
        if callable(restore_remote_mode):
            restore_remote_mode()
        self.notify("Remote API reconnected")

    def _handle_remote_sync_error(
        self,
        worker: Worker[RemoteSyncResult],
    ) -> None:
        """Apply UI state updates after a failed remote sync."""
        self._clear_sync_indicator()
        message = (
            str(worker.error)
            if worker.error is not None
            else "Remote sync failed"
        )
        if self._initial_remote_sync_pending:
            self._initial_remote_sync_pending = False
            self._show_remote_startup_recovery(message)
            return
        if self._remote_cached_read_only:
            self._remote_sync_error = message
            return
        if message != self._remote_sync_error:
            self.notify(message, severity="error")
        self._remote_sync_error = message

    def _show_remote_startup_recovery(self, message: str) -> None:
        """Open the startup recovery modal for an initial remote failure."""
        if self._remote_startup_modal_open:
            return
        self._remote_startup_modal_open = True
        self.app.push_screen(
            RemoteStartupRecoveryScreen(message),
            callback=self._on_remote_startup_recovery_dismiss,
        )

    def _on_remote_startup_recovery_dismiss(self, result: object) -> None:
        """Handle the recovery action chosen after remote startup fails."""
        self._remote_startup_modal_open = False
        if not isinstance(result, RemoteStartupRecoveryAction):
            return
        if result == RemoteStartupRecoveryAction.RETRY:
            self._set_remote_cached_read_only(read_only=False)
            restore_remote_mode = getattr(
                self.app,
                "restore_remote_mode",
                None,
            )
            if callable(restore_remote_mode):
                restore_remote_mode()
            self._initial_remote_sync_pending = True
            self._request_remote_sync()
            return
        if result == RemoteStartupRecoveryAction.USE_CACHE:
            self._set_remote_cached_read_only(read_only=True)
            activate_cached_remote_mode = getattr(
                self.app,
                "activate_cached_remote_mode",
                None,
            )
            if callable(activate_cached_remote_mode):
                activate_cached_remote_mode()
            self.refresh_ideas(select_pk=self._selected_idea_pk)
            return
        if result == RemoteStartupRecoveryAction.SWITCH_LOCAL:
            activate_local_fallback = getattr(
                self.app,
                "activate_session_local_fallback",
                None,
            )
            if callable(activate_local_fallback):
                activate_local_fallback()
                self.notify("Using local mode for this session")
            else:
                self.notify(
                    "Local fallback is unavailable",
                    severity="error",
                )
            return
        self.app.exit()

    def _refresh_after_remote_sync(self) -> None:
        """Refresh visible state while preserving current selection."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        selected_group_pk = panel.get_selected_group_pk()
        self.refresh_ideas(
            select_pk=self._selected_idea_pk,
            select_group_pk=selected_group_pk,
        )

    def _set_sync_indicator(self) -> None:
        """Show a subtle syncing indicator in the app subtitle."""
        self.app.sub_title = f"{self._base_sub_title} | Syncing..."

    def _clear_sync_indicator(self) -> None:
        """Restore the default subtitle after a sync completes."""
        self.app.sub_title = self._base_sub_title

    def _handle_remote_clone_success(self) -> None:
        """Apply UI updates after a successful remote-to-local clone."""
        self._dismiss_remote_clone_progress()
        self._remote_clone_worker = None
        if not self._clone_started_in_remote_mode:
            self.refresh_ideas(select_pk=self._selected_idea_pk)
            self.notify("Local database replaced from remote snapshot")
            return

        should_prompt_getter = getattr(
            self.app,
            "should_prompt_after_clone",
            None,
        )
        should_prompt = (
            should_prompt_getter() if callable(should_prompt_getter) else False
        )
        if should_prompt:
            self.app.push_screen(
                RemoteCloneSwitchModeScreen(),
                callback=self._on_remote_clone_switch_dismiss,
            )
        else:
            self.notify("Local database replaced from remote snapshot")

    def _handle_remote_clone_error(self, worker: Worker[None]) -> None:
        """Apply UI updates after a failed remote-to-local clone."""
        self._dismiss_remote_clone_progress()
        self._remote_clone_worker = None
        message = (
            str(worker.error)
            if worker.error is not None
            else "Remote clone failed"
        )
        self.notify(message, severity="error")

    def _dismiss_remote_clone_progress(self) -> None:
        """Close the clone progress modal when it is currently mounted."""
        progress_screen = self._remote_clone_progress_screen
        self._remote_clone_progress_screen = None
        if progress_screen is None:
            return
        if self.app.screen is progress_screen:
            self.app.pop_screen()

    def _on_remote_clone_switch_dismiss(self, result: object) -> None:
        """Handle the optional local-mode switch after clone success."""
        if result != RemoteCloneModeAction.SWITCH_LOCAL:
            self.notify("Local database replaced from remote snapshot")
            return
        get_backend_config = getattr(self.app, "get_backend_config", None)
        apply_backend_config = getattr(self.app, "apply_backend_config", None)
        if callable(get_backend_config) and callable(apply_backend_config):
            apply_backend_config(
                replace(
                    get_backend_config(),
                    mode=DataBackendMode.LOCAL,
                )
            )
            self.notify("Switched to local mode")
            return
        self.notify("Local fallback is unavailable", severity="error")

    def _update_remote_clone_progress(
        self,
        progress: SnapshotImportProgress,
    ) -> None:
        """Update the clone progress modal from worker-thread callbacks."""
        progress_screen = self._remote_clone_progress_screen
        if progress_screen is None or not progress_screen.is_mounted:
            return
        if progress.stage == "Download":
            if progress.completed >= progress.total and progress.total > 0:
                progress_screen.mark_download_complete()
            return
        progress_screen.update_stage_progress(
            stage=progress.stage,
            completed=progress.completed,
            total=progress.total,
        )

    @work(thread=True, exclusive=True, exit_on_error=False)
    def _run_remote_clone(self) -> None:
        """Clone the current remote snapshot into the local database."""
        clone_remote_to_local = getattr(self.app, "clone_remote_to_local", None)
        if not callable(clone_remote_to_local):
            msg = "Remote clone is unavailable"
            raise TypeError(msg)
        clone_remote_to_local(
            progress_callback=lambda progress: self.app.call_from_thread(
                self._update_remote_clone_progress,
                progress,
            )
        )

    def _refresh_relative_timestamps(self) -> None:
        """Refresh in-place relative timestamps in the visible idea tree."""
        self.query_one(
            "#idea-list-panel",
            IdeaListPanel,
        ).refresh_relative_timestamps()

    def refresh_ideas(
        self,
        select_pk: int | None = None,
        *,
        select_group_pk: int | None = None,
    ) -> None:
        """Reload the idea list from the service."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        panel.set_autocomplete_sources(
            tags=[tag.name for tag in self._service.list_tags_in_use()],
            groups=[group.name for group in self._service.list_groups()],
        )
        raw_search_query = panel.raw_search_query()
        search_query = raw_search_query.strip()
        if raw_search_query:
            if search_query:
                self._refresh_search_results(
                    panel,
                    search_query=search_query,
                    select_pk=select_pk,
                )
            return

        local_select_pk = select_pk
        if local_select_pk is None and select_group_pk is None:
            local_select_pk = self._selected_idea_pk

        view = self.query_one("#content-panel", IdeaView)
        grouped_ideas = self._service.list_ideas_grouped(None)
        panel.load_grouped_ideas(
            grouped_ideas,
            auto_select_first=select_group_pk is None,
        )
        self._refresh_grouped_ideas(
            panel,
            view,
            grouped_ideas=grouped_ideas,
            select_pk=local_select_pk,
            select_group_pk=select_group_pk,
        )

    def _refresh_grouped_ideas(
        self,
        panel: IdeaListPanel,
        view: IdeaView,
        *,
        grouped_ideas: list[tuple[Group, list[Idea]]],
        select_pk: int | None,
        select_group_pk: int | None,
    ) -> None:
        """Refresh normal grouped-idea tree state and right-pane preview."""
        has_ideas = any(group_ideas for _, group_ideas in grouped_ideas)
        if has_ideas:
            restored_idea = select_pk is not None and panel.select_idea(
                select_pk
            )
            if not restored_idea and not self._restore_group_selection(
                panel,
                view,
                select_group_pk=select_group_pk,
            ):
                return
            self._sync_panel_selection_preview(
                panel,
                view,
                commit_selection=True,
            )
        else:
            if not self._restore_group_selection(
                panel,
                view,
                select_group_pk=select_group_pk,
            ):
                return
            self._show_idea_preview(
                view,
                None,
                commit_selection=True,
            )

    def _restore_group_selection(
        self,
        panel: IdeaListPanel,
        view: IdeaView,
        *,
        select_group_pk: int | None,
    ) -> bool:
        """Restore requested group selection or clear the preview on failure."""
        if select_group_pk is None or panel.select_group(select_group_pk):
            return True
        self._clear_selected_idea_view(view)
        return False

    def _clear_selected_idea_view(self, view: IdeaView) -> None:
        """Clear the selected idea and show an empty preview pane."""
        self._show_idea_preview(
            view,
            None,
            commit_selection=True,
        )

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
            search_query=search_query,
        )
        matched_select_pk = False
        if select_pk is not None and any(
            result.idea.pk == select_pk for result in search_results
        ):
            matched_select_pk = panel.select_idea(select_pk)
        self._show_search_selection_preview(
            panel,
            commit_selection=(
                matched_select_pk or panel.is_search_results_focused()
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
        self._sync_panel_selection_preview(
            panel,
            view,
            commit_selection=commit_selection,
        )

    def on_idea_list_panel_idea_selected(
        self, event: IdeaListPanel.IdeaSelected
    ) -> None:
        """Update detail view when an idea is selected."""
        view = self.query_one("#content-panel", IdeaView)
        fresh = self._service.get_idea(event.idea.pk)
        self._show_idea_preview(
            view,
            fresh,
            commit_selection=True,
        )

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
                search_query=query,
            )
            self._show_search_selection_preview(
                panel,
                commit_selection=False,
            )
            return

        grouped_ideas = self._service.list_ideas_grouped(None)
        panel.load_grouped_ideas(grouped_ideas)
        if self._selected_idea_pk is not None:
            panel.select_idea(self._selected_idea_pk)
        self._sync_panel_selection_preview(
            panel,
            view,
            commit_selection=True,
        )

    def _sync_panel_selection_preview(
        self,
        panel: IdeaListPanel,
        view: IdeaView,
        *,
        commit_selection: bool,
    ) -> None:
        """Show the panel's selected idea in the preview pane."""
        self._show_idea_preview(
            view,
            panel.get_selected_idea(),
            commit_selection=commit_selection,
        )

    def _show_idea_preview(
        self,
        view: IdeaView,
        idea: Idea | None,
        *,
        commit_selection: bool,
    ) -> None:
        """Show one idea in the preview pane, or the empty state."""
        self._save_current_idea_scroll(view)
        if commit_selection:
            self._set_selected_idea(None if idea is None else idea.pk)
        if idea is None:
            view.show_empty()
            return
        scroll_y = self._saved_scroll_y_for_idea(idea)
        if scroll_y is None:
            view.show_idea(idea)
            return
        view.show_idea(idea, scroll_y=scroll_y)

    def _save_current_idea_scroll(self, view: IdeaView) -> None:
        """Persist current rendered-pane scroll position when enabled."""
        if not self._preserve_idea_scroll_position:
            return
        state = view.current_scroll_state()
        if state is None:
            return
        idea_pk, detail_hash, scroll_y = state
        self._service.set_idea_scroll_position(
            idea_pk,
            detail_hash,
            scroll_y,
        )

    def _saved_scroll_y_for_idea(self, idea: Idea) -> int | None:
        """Return saved rendered-pane scroll position when enabled."""
        if not self._preserve_idea_scroll_position:
            return None
        return self._service.get_idea_scroll_position(
            idea.pk,
            idea.detail_hash,
        )

    def _ensure_mutation_allowed(self) -> bool:
        """Return whether mutating actions are allowed right now."""
        if not self._remote_cached_read_only:
            return True
        self.notify(
            "Cached remote data is read-only while the API is unavailable",
            severity="warning",
        )
        return False

    def action_new_idea(self) -> None:
        """Open the new idea form."""
        if not self._ensure_mutation_allowed():
            return
        initial_group_pk = None
        if self._new_idea_group_mode == NewIdeaGroupMode.CONTEXTUAL:
            initial_group_pk = self._get_contextual_new_idea_group_pk()
        self.app.push_screen(
            IdeaFormScreen(
                self._service,
                initial_group_pk=initial_group_pk,
                edit_body_cursor_mode=self._edit_body_cursor_mode,
                on_saved=self._on_form_saved,
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
        if not self._ensure_mutation_allowed():
            return
        self.app.push_screen(
            GroupFormScreen(self._service),
            callback=self._on_group_form_dismiss,
        )

    def action_new_subgroup(self) -> None:
        """Open the new subgroup form."""
        if not self._ensure_mutation_allowed():
            return
        parent_pk = self._get_contextual_new_idea_group_pk()
        if parent_pk is None:
            parent_pk = self._get_default_group_pk()
        self.app.push_screen(
            GroupFormScreen(
                self._service,
                parent_pk=parent_pk,
                show_parent_select=True,
            ),
            callback=self._on_group_form_dismiss,
        )

    def _get_default_group_pk(self) -> int | None:
        """Return the default group primary key if available."""
        for group in self._service.list_groups():
            if group.name == self._service.default_group_name:
                return group.pk
        return None

    def action_edit_idea(self) -> None:
        """Open the edit form for the selected idea."""
        if not self._ensure_mutation_allowed():
            return
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        idea = panel.get_selected_idea()
        if idea is None:
            self.notify("No idea selected", severity="warning")
            return
        self._sync_remote_before_edit(lambda: self._open_edit_idea(idea.pk))

    def _open_edit_idea(self, idea_pk: int) -> None:
        """Open the edit form using freshly synced data."""
        fresh = self._service.get_idea(idea_pk)
        if fresh is None:
            self.notify("Idea not found", severity="error")
            return
        self.app.push_screen(
            IdeaFormScreen(
                self._service,
                idea=fresh,
                edit_body_cursor_mode=self._edit_body_cursor_mode,
                on_saved=self._on_form_saved,
            ),
            callback=self._on_form_dismiss,
        )

    def action_delete_idea(self) -> None:
        """Delete the selected idea with confirmation."""
        if not self._ensure_mutation_allowed():
            return
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

    def action_rename_selected(self) -> None:
        """Rename the currently selected group or idea."""
        if not self._ensure_mutation_allowed():
            return
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        group_pk = panel.get_selected_group_pk()
        if group_pk is not None:
            self._rename_selected_group(group_pk)
            return

        idea = panel.get_selected_idea()
        if idea is None:
            self.notify("Nothing renameable selected", severity="warning")
            return
        self._rename_selected_idea(idea.pk)

    def _rename_selected_group(self, group_pk: int) -> None:
        """Open rename flow for a selected group."""
        self._sync_remote_before_edit(lambda: self._open_group_rename(group_pk))

    def _open_group_rename(self, group_pk: int) -> None:
        """Open rename flow for a selected group after sync completes."""
        group = self._service.get_group(group_pk)
        if group is None:
            self.notify("Group not found", severity="error")
            return
        if group.name == self._service.default_group_name:
            self.notify(
                "Default group cannot be renamed",
                severity="warning",
            )
            return
        self.app.push_screen(
            NameInputScreen(
                title="Rename Group",
                initial_value=group.name,
                placeholder="Group name...",
            ),
            callback=lambda name: self._on_group_rename_dismiss(
                group.pk,
                name,
            ),
        )

    def _rename_selected_idea(self, idea_pk: int) -> None:
        """Open rename flow for a selected idea."""
        self._sync_remote_before_edit(lambda: self._open_idea_rename(idea_pk))

    def _open_idea_rename(self, idea_pk: int) -> None:
        """Open rename flow for a selected idea after sync completes."""
        fresh = self._service.get_idea(idea_pk)
        if fresh is None:
            self.notify("Idea not found", severity="error")
            return
        self.app.push_screen(
            NameInputScreen(
                title="Rename Idea",
                initial_value=fresh.title,
                placeholder="Idea title...",
            ),
            callback=lambda title: self._on_idea_rename_dismiss(
                fresh.pk,
                title,
            ),
        )

    def _sync_remote_before_edit(
        self,
        on_ready: Callable[[], None] | None = None,
    ) -> bool:
        """Refresh remote-backed data before opening edit-style flows."""
        if self._remote_cached_read_only:
            self.notify(
                "Cached remote data is read-only while the API is unavailable",
                severity="warning",
            )
            return False
        backend = self._syncing_backend()
        if backend is None:
            if on_ready is not None:
                on_ready()
            return True
        if on_ready is not None:
            self._pending_pre_edit_action = on_ready
        if self._remote_sync_in_progress():
            return False
        self._set_sync_indicator()
        self._remote_sync_worker = self._run_remote_sync()
        return False

    def _run_pending_pre_edit_action(self) -> None:
        """Continue a deferred edit flow once remote sync succeeds."""
        action = self._pending_pre_edit_action
        self._pending_pre_edit_action = None
        if action is not None:
            action()

    def action_delete_group(self) -> None:
        """Delete selected group with optional bulk move."""
        if not self._ensure_mutation_allowed():
            return
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
        if any(item.parent_pk == group_pk for item in groups):
            self.notify(
                "Group with child groups cannot be deleted",
                severity="warning",
            )
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
        idea, had_target = self._resolve_copy_target_idea()
        if idea is None:
            if had_target:
                self.notify("Idea not found", severity="error")
            else:
                self.notify("No idea selected", severity="warning")
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

    def _resolve_copy_target_idea(self) -> tuple[Idea | None, bool]:
        """Return the idea that copy-body actions should target."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        if panel.search_is_active():
            selected = panel.get_selected_idea()
            if selected is None:
                return None, False
            return self._service.get_idea(selected.pk), True
        if self._selected_idea_pk is None:
            return None, False
        return self._service.get_idea(self._selected_idea_pk), True

    def _get_selected_rendered_body_text(self) -> str | None:
        """Return selected text in rendered body, if any."""
        selected_text = self.get_selected_text()
        if selected_text:
            return selected_text

        view = self.query_one("#content-panel", IdeaView)
        return view.selected_body_text()

    def _on_delete_confirm(
        self,
        pk: int,
        *,
        confirmed: bool,
    ) -> None:
        """Handle delete confirmation result."""
        if confirmed:
            if not self._ensure_mutation_allowed():
                return
            self._service.delete_idea(pk)
            self.notify("Idea deleted")
            self.refresh_ideas()

    def _on_form_dismiss(self, result: int | None) -> None:
        """Handle form dismiss — result is the idea pk."""
        if result is not None:
            self.refresh_ideas(select_pk=result)

    def _on_form_saved(self, idea_pk: int) -> None:
        """Refresh the visible idea after a stay-open form save."""
        self.refresh_ideas(select_pk=idea_pk)

    def _on_group_form_dismiss(self, result: int | None) -> None:
        """Refresh tree after group create."""
        if result is not None:
            self.notify("Group created")
            self.refresh_ideas()

    def _on_group_rename_dismiss(
        self,
        group_pk: int,
        name: str | None,
    ) -> None:
        """Handle group rename flow completion."""
        if name is None:
            return
        if not self._ensure_mutation_allowed():
            return
        try:
            renamed = self._service.rename_group(group_pk, name)
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        if renamed is None:
            self.notify("Group not found", severity="error")
            return
        self.notify("Group renamed")
        self.refresh_ideas(select_group_pk=renamed.pk)

    def _on_idea_rename_dismiss(
        self,
        idea_pk: int,
        title: str | None,
    ) -> None:
        """Handle idea rename flow completion."""
        if title is None:
            return
        if not self._ensure_mutation_allowed():
            return
        try:
            renamed = self._service.rename_idea(idea_pk, title)
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        if renamed is None:
            self.notify("Idea not found", severity="error")
            return
        self.notify("Idea renamed")
        self.refresh_ideas(select_pk=renamed.pk)

    def _on_delete_group_confirm(
        self,
        group_pk: int,
        *,
        confirmed: bool,
    ) -> None:
        """Handle delete-group confirmation for empty groups."""
        if confirmed:
            if not self._ensure_mutation_allowed():
                return
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
        if not self._ensure_mutation_allowed():
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

    def action_search_by_tag(self, tag_name: str) -> None:
        """Set search to tag:<tag_name> and focus the search input."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        if not panel.is_search_input_focused():
            self._focus_before_search = self._active_pane
        panel.set_search_query(f"tag:{shlex_quote(tag_name)}")

    def action_focus_search(self) -> None:
        """Focus the search input."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        if not panel.is_search_input_focused():
            self._focus_before_search = self._active_pane
        panel.focus_search()

    def action_cancel_search(self) -> None:
        """Clear search and return focus to the previous panel."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        cancel_result = panel.cancel_search_interaction()
        if cancel_result != "cleared_search":
            return
        if self._focus_before_search == "content":
            self.query_one("#content-panel", IdeaView).focus_content()
            self._active_pane = "content"
        else:
            panel.focus_preferred_list_widget()
            self._active_pane = "list"

    def action_show_help(self) -> None:
        """Show the help overlay."""
        self.app.push_screen(HelpScreen())

    def action_clone_remote_to_local(self) -> None:
        """Confirm and start a destructive remote-to-local clone."""
        if self._remote_clone_in_progress():
            self.notify("Remote clone already in progress", severity="warning")
            return
        self.app.push_screen(
            ConfirmDialog(
                "Clone the current remote snapshot into the local database?\n\n"
                "This will overwrite the existing local database."
            ),
            callback=self._on_clone_remote_to_local_confirm,
        )

    def _on_clone_remote_to_local_confirm(self, confirmed: object) -> None:
        """Start the clone only after explicit user confirmation."""
        if confirmed is not True:
            return
        self._clone_started_in_remote_mode = self._syncing_backend() is not None
        progress_screen = RemoteCloneProgressScreen()
        self._remote_clone_progress_screen = progress_screen
        self.app.push_screen(progress_screen)
        self._remote_clone_worker = self._run_remote_clone()

    def _remote_clone_in_progress(self) -> bool:
        """Return whether a remote-to-local clone worker is still running."""
        worker = self._remote_clone_worker
        return worker is not None and not worker.is_finished

    def action_show_backend_config(self) -> None:
        """Show the backend configuration modal."""
        getter = getattr(self.app, "get_backend_config", None)
        if getter is None:
            self.notify("Backend settings are unavailable", severity="error")
            return
        config = getter()
        self.app.push_screen(
            BackendConfigScreen(config),
            callback=self._on_backend_config_dismiss,
        )

    def _on_backend_config_dismiss(self, config: object) -> None:
        """Apply backend configuration changes from the modal."""
        if not isinstance(config, BackendConfig):
            return
        apply_backend_config = getattr(self.app, "apply_backend_config", None)
        if apply_backend_config is None:
            self.notify("Backend settings are unavailable", severity="error")
            return
        apply_backend_config(config)
        self.notify("Connection settings updated")

    def action_show_about(self) -> None:
        """Show the About overlay."""
        self.app.push_screen(AboutScreen(self._app_metadata))

    def action_toggle_focus(self) -> None:
        """Toggle focus between list and content panes."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)
        if panel.is_search_input_focused():
            return
        if panel.has_focus_within:
            content = self.query_one("#content-panel", IdeaView)
            content.focus_content()
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
            content.focus_content()
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
        search_is_active = panel.search_is_active()
        search_input_focused = panel.is_search_input_focused()
        search_results_focused = panel.is_search_results_focused()
        if (
            self._remote_cached_read_only
            and action in self._REMOTE_READ_ONLY_ACTIONS
        ):
            return False

        if search_is_active:
            if (
                search_input_focused or search_results_focused
            ) and action in self._SEARCH_MODE_DISABLED_ACTIONS:
                return False
            if (
                search_input_focused
                and action in self._SEARCH_INPUT_DISABLED_ACTIONS
            ):
                return False

        result: bool | None
        if action == "footer_search_results":
            result = (
                search_input_focused
                and search_is_active
                and not panel.autocomplete_is_visible()
                and bool(panel.get_selected_idea())
            )
        elif action == "footer_exit_search":
            result = search_input_focused
        elif action == "rename_selected":
            result = self._can_rename_selection()
        else:
            result = super().check_action(action, parameters)
        return result

    def _can_rename_selection(self) -> bool:
        """Return whether the current focus/selection supports rename."""
        panel = self.query_one("#idea-list-panel", IdeaListPanel)

        if panel.is_search_input_focused():
            return False
        group_pk = panel.get_selected_group_pk()
        if group_pk is not None:
            group = self._service.get_group(group_pk)
            return (
                group is not None
                and group.name != self._service.default_group_name
            )
        return panel.get_selected_idea() is not None

    @property
    def active_bindings(self) -> dict[str, ActiveBinding]:
        """Return bindings with search-mode footer filtering."""
        bindings = super().active_bindings
        panel = self.query_one("#idea-list-panel", IdeaListPanel)

        if panel.is_search_input_focused() or panel.search_is_active():
            bindings = {
                key: binding
                for key, binding in bindings.items()
                if binding.binding.action != "toggle_focus"
            }

        if panel.is_search_input_focused() and not panel.search_is_active():
            bindings = {
                key: binding
                for key, binding in bindings.items()
                if binding.binding.action == "footer_exit_search"
            }
        elif panel.is_search_input_focused() and panel.search_is_active():
            bindings = {
                key: binding
                for key, binding in bindings.items()
                if binding.binding.action in self._SEARCH_INPUT_FOOTER_ACTIONS
            }
        elif panel.is_search_results_focused() and panel.search_is_active():
            bindings = {
                key: binding
                for key, binding in bindings.items()
                if binding.binding.action in self._SEARCH_RESULTS_FOOTER_ACTIONS
            }

        up_binding = bindings.get("up")
        if (
            panel.is_search_results_focused()
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

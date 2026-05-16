"""Cogitus Textual application."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import App, InvalidThemeError, ScreenStackError, SystemCommand

from cogitus.backends import (
    BackendConfig,
    IdeaBackend,
    RemoteAPIClient,
    RemoteIdeaBackend,
)
from cogitus.config import (
    DEFAULT_THEME,
    VALID_DATE_FORMATS,
    VALID_NEW_IDEA_GROUP_MODES,
    DataBackendMode,
    get_settings,
    is_valid_date_format,
    is_valid_timezone,
    normalize_data_backend_mode,
    normalize_date_format,
    normalize_default_group_name,
    normalize_edit_body_cursor_mode,
    normalize_new_idea_group_mode,
    normalize_remote_api_base_url,
    normalize_timezone,
)
from cogitus.db import DEFAULT_DB_PATH, get_db
from cogitus.metadata import get_app_metadata
from cogitus.repositories.group_repo import GroupRepository
from cogitus.repositories.snapshot_import_repo import (
    SnapshotImportCallback,
    SnapshotImportProgress,
    SnapshotImportRepository,
)
from cogitus.services.idea_service import IdeaService
from cogitus.ui.screens.main_screen import MainScreen

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Any, Protocol

    from rich.console import RenderableType
    from sqliter import SqliterDB
    from textual.screen import Screen

    class SettingsLike(Protocol):
        """Settings interface required by the app."""

        last_viewed_idea_pk: int
        theme: str
        edit_body_cursor_mode: str
        new_idea_group_mode: str
        default_group_name: str
        data_backend_mode: str
        remote_api_base_url: str
        remote_api_username: str
        remote_api_password: str
        prompt_after_clone: bool
        timezone: str
        date_format: str
        preserve_idea_scroll_position: bool

        def set(
            self,
            key: str,
            value: object,
            *,
            autosave: bool = True,
        ) -> None:
            """Persist one setting value via the settings API."""

        def save(self) -> None:
            """Persist settings."""


CSS_PATH = Path(__file__).parent / "ui" / "styles" / "app.tcss"
DEFAULT_REMOTE_CACHE_DB_PATH = "~/.config/cogitus/cogitus-remote-cache.db"


@dataclass(frozen=True)
class _DatabaseHandle:
    """Database connection plus ownership metadata."""

    db: SqliterDB
    owns_db: bool


class CogitusApp(App[None]):
    """Cogitus — a terminal workspace for programming ideas."""

    TITLE = "Cogitus"
    SUB_TITLE = "Idea Workspace"

    def __init__(
        self,
        db_path: str | None = None,
        db: SqliterDB | None = None,
        settings: SettingsLike | None = None,
        backend: IdeaBackend | None = None,
    ) -> None:
        """Initialize the Cogitus application.

        Args:
            db_path: Path to the database file.
            db: Pre-configured database instance (for testing).
            settings: Optional settings instance (for testing).
            backend: Optional pre-built backend (for testing).
        """
        super().__init__(css_path=CSS_PATH)
        self._app_metadata = get_app_metadata()
        self.sub_title = self.SUB_TITLE
        self._db_path = db_path
        self._injected_db = db
        self._settings = settings if settings is not None else get_settings()
        self._theme: str
        self._load_settings_state()
        try:
            self.theme = self._theme
        except InvalidThemeError:
            self._theme = DEFAULT_THEME
            self.theme = self._theme
            self._settings.set("theme", self._theme)
        self._session_backend_mode_override: DataBackendMode | None = None
        self._remote_runtime_offline = False
        self._update_title()
        last_viewed = self._settings.last_viewed_idea_pk
        self._last_viewed_idea_pk = last_viewed if last_viewed > 0 else None
        self._db: SqliterDB | None = None
        self._owns_db = False
        if backend is None:
            handle = self._build_backend_db(
                db_path=db_path,
                db=db,
            )
            self._db = handle.db
            self._owns_db = handle.owns_db
        else:
            self._db = db
        self._service = backend or self._build_backend()

    def _load_settings_state(self) -> None:
        """Load and normalize persisted settings values."""
        configured_theme = self._settings.theme.strip()
        self._theme = configured_theme or DEFAULT_THEME
        self._edit_body_cursor_mode = normalize_edit_body_cursor_mode(
            self._settings.edit_body_cursor_mode
        )
        configured_new_idea_mode = self._settings.new_idea_group_mode
        self._configured_new_idea_group_mode = configured_new_idea_mode
        self._new_idea_group_mode = normalize_new_idea_group_mode(
            configured_new_idea_mode
        )
        configured_default_group_name = self._settings.default_group_name
        self._configured_default_group_name = configured_default_group_name
        self._default_group_name = normalize_default_group_name(
            configured_default_group_name
        )
        configured_backend_mode = self._settings.data_backend_mode
        self._configured_data_backend_mode = configured_backend_mode
        self._data_backend_mode = normalize_data_backend_mode(
            configured_backend_mode
        )
        self._prompt_after_clone = bool(self._settings.prompt_after_clone)
        self._remote_api_base_url = normalize_remote_api_base_url(
            self._settings.remote_api_base_url
        )
        self._remote_api_username = self._settings.remote_api_username.strip()
        self._remote_api_password = self._settings.remote_api_password
        self._invalid_new_idea_group_mode = (
            configured_new_idea_mode != self._new_idea_group_mode.value
        )
        self._invalid_default_group_name = (
            not configured_default_group_name.strip()
        )
        self._invalid_data_backend_mode = (
            configured_backend_mode != self._data_backend_mode.value
        )
        self._configured_timezone = self._settings.timezone
        self._timezone = normalize_timezone(self._settings.timezone)
        self._configured_date_format = self._settings.date_format
        self._date_format = normalize_date_format(self._settings.date_format)
        self._preserve_idea_scroll_position = bool(
            self._settings.preserve_idea_scroll_position
        )
        self._invalid_timezone = not is_valid_timezone(
            self._configured_timezone
        )
        self._invalid_date_format = not is_valid_date_format(
            self._configured_date_format
        )

    def on_mount(self) -> None:
        """Push the main screen on mount."""
        self.push_screen(self._build_main_screen())
        self._notify_invalid_config()

    def watch_theme(self, theme: str) -> None:
        """Persist theme changes to settings immediately."""
        if self._settings.theme == theme:
            return
        self._settings.set("theme", theme)

    def get_system_commands(
        self,
        screen: Screen[Any],
    ) -> Iterable[SystemCommand]:
        """Expose app-specific commands in the Textual command palette."""
        yield from super().get_system_commands(screen)
        if isinstance(screen, MainScreen):
            yield SystemCommand(
                "Backend settings",
                "Configure the local or remote data backend",
                screen.action_show_backend_config,
            )
            yield SystemCommand(
                "Clone Remote To Local",
                "Overwrite the local database with a fresh remote snapshot",
                screen.action_clone_remote_to_local,
            )

    def _backend_title_suffix(self) -> str:
        """Return the current backend mode label for the app title."""
        if self._active_backend_mode() == DataBackendMode.API:
            if self._remote_runtime_offline:
                return "remote: offline"
            return "remote"
        return "local"

    def _active_backend_mode(self) -> DataBackendMode:
        """Return the active runtime backend mode."""
        if self._session_backend_mode_override is not None:
            return self._session_backend_mode_override
        return self._data_backend_mode

    def _update_title(self) -> None:
        """Refresh the visible app title for the active backend mode."""
        self.title = (
            f"{self._app_metadata.title} [{self._backend_title_suffix()}]"
        )
        try:
            screen = self.screen
        except ScreenStackError:
            return
        if isinstance(screen, MainScreen):
            screen.title = self.title

    def _build_local_db(
        self,
        *,
        db_path: str | None,
        db: SqliterDB | None,
    ) -> _DatabaseHandle:
        """Return the local database handle and ownership metadata."""
        if db is not None:
            GroupRepository(db).get_or_create(self._default_group_name)
            return _DatabaseHandle(db=db, owns_db=False)
        if db_path is not None:
            return _DatabaseHandle(
                db=get_db(
                    db_path,
                    default_group_name=self._default_group_name,
                ),
                owns_db=True,
            )
        return _DatabaseHandle(
            db=get_db(default_group_name=self._default_group_name),
            owns_db=True,
        )

    def _build_remote_cache_db(
        self,
        *,
        db_path: str | None,
        db: SqliterDB | None,
    ) -> _DatabaseHandle:
        """Return the remote-cache database handle and ownership metadata."""
        if db is not None:
            GroupRepository(db).get_or_create(self._default_group_name)
            return _DatabaseHandle(db=db, owns_db=False)
        cache_path = db_path or DEFAULT_REMOTE_CACHE_DB_PATH
        return _DatabaseHandle(
            db=get_db(
                cache_path,
                default_group_name=self._default_group_name,
            ),
            owns_db=True,
        )

    def _build_backend_db(
        self,
        *,
        db_path: str | None,
        db: SqliterDB | None,
        mode: DataBackendMode | None = None,
    ) -> _DatabaseHandle:
        """Build the backend DB handle for the selected mode."""
        resolved_mode = self._active_backend_mode() if mode is None else mode
        if resolved_mode == DataBackendMode.API:
            return self._build_remote_cache_db(db_path=db_path, db=db)
        return self._build_local_db(db_path=db_path, db=db)

    def _close_owned_db(self) -> None:
        """Close the current database when the app owns the connection."""
        if self._db is None or not self._owns_db:
            return
        self._db.close()
        self._db = None
        self._owns_db = False

    def _replace_backend(self, *, mode: DataBackendMode) -> None:
        """Rebuild the active backend and swap in the correct database."""
        new_handle: _DatabaseHandle | None = None
        try:
            new_handle = self._build_backend_db(
                db_path=self._db_path,
                db=self._injected_db,
                mode=mode,
            )
            new_service = self._build_backend(
                db=new_handle.db,
                mode=mode,
            )
        except Exception:
            if new_handle is not None and new_handle.owns_db:
                new_handle.db.close()
            raise

        old_service = self._service
        old_db = self._db
        old_owns_db = self._owns_db
        self._db = new_handle.db
        self._owns_db = new_handle.owns_db
        self._service = new_service

        if isinstance(old_service, RemoteIdeaBackend):
            old_service.close()
        if old_db is not None and old_owns_db:
            old_db.close()

    def _build_backend(
        self,
        *,
        db: SqliterDB | None = None,
        mode: DataBackendMode | None = None,
    ) -> IdeaBackend:
        """Build the configured local or remote backend implementation."""
        resolved_db = self._db if db is None else db
        if resolved_db is None:
            msg = "Backend database is not initialized"
            raise RuntimeError(msg)
        resolved_mode = self._active_backend_mode() if mode is None else mode
        if resolved_mode == DataBackendMode.API:
            client = RemoteAPIClient(
                base_url=self._remote_api_base_url,
                username=self._remote_api_username,
                password=self._remote_api_password,
            )
            return RemoteIdeaBackend(
                resolved_db,
                default_group_name=self._default_group_name,
                api_client=client,
            )
        return IdeaService(
            resolved_db,
            default_group_name=self._default_group_name,
        )

    def get_backend_config(self) -> BackendConfig:
        """Return the current backend configuration snapshot."""
        return BackendConfig(
            mode=self._active_backend_mode(),
            api_base_url=self._remote_api_base_url,
            api_username=self._remote_api_username,
            api_password=self._remote_api_password,
        )

    def apply_backend_config(self, config: BackendConfig) -> None:
        """Persist backend settings and rebuild the active backend."""
        self._settings.set(
            "data_backend_mode",
            config.mode.value,
            autosave=False,
        )
        self._settings.set(
            "remote_api_base_url",
            config.api_base_url,
            autosave=False,
        )
        self._settings.set(
            "remote_api_username",
            config.api_username,
            autosave=False,
        )
        self._settings.set(
            "remote_api_password",
            config.api_password,
            autosave=False,
        )
        self._settings.save()
        self._load_settings_state()
        self._session_backend_mode_override = None
        self._remote_runtime_offline = False
        self._update_title()
        self._replace_backend(mode=self._data_backend_mode)
        if isinstance(self.screen, MainScreen):
            self.screen.replace_service(self._service)
        self._notify_invalid_config()

    def activate_cached_remote_mode(self) -> None:
        """Mark the active remote backend as temporarily offline."""
        if self._active_backend_mode() != DataBackendMode.API:
            return
        self._remote_runtime_offline = True
        self._update_title()

    def restore_remote_mode(self) -> None:
        """Clear the temporary offline state for the remote backend."""
        if self._active_backend_mode() != DataBackendMode.API:
            return
        self._remote_runtime_offline = False
        self._update_title()

    def activate_session_local_fallback(self) -> None:
        """Switch to local mode for the current session only."""
        self._session_backend_mode_override = DataBackendMode.LOCAL
        self._remote_runtime_offline = False
        self._replace_backend(mode=DataBackendMode.LOCAL)
        self._update_title()
        if isinstance(self.screen, MainScreen):
            self.screen.replace_service(self._service)

    def should_prompt_after_clone(self) -> bool:
        """Return whether remote-mode clone should prompt for local switch."""
        return self._prompt_after_clone

    def clone_remote_to_local(
        self,
        *,
        progress_callback: SnapshotImportCallback | None = None,
    ) -> None:
        """Replace the local database with a fresh remote snapshot."""
        if not self._remote_api_base_url:
            msg = "Remote API is not fully configured"
            raise RuntimeError(msg)

        client = RemoteAPIClient(
            base_url=self._remote_api_base_url,
            username=self._remote_api_username,
            password=self._remote_api_password,
        )
        target_db = None
        try:
            if progress_callback is not None:
                progress_callback(
                    SnapshotImportProgress(
                        stage="Download",
                        completed=0,
                        total=0,
                    )
                )
            snapshot = client.fetch_snapshot()
            if progress_callback is not None:
                progress_callback(
                    SnapshotImportProgress(
                        stage="Download",
                        completed=1,
                        total=1,
                    )
                )
            target_db = get_db(
                self._resolve_clone_target_local_db_path(),
                default_group_name=self._default_group_name,
            )
            SnapshotImportRepository(target_db).replace_snapshot(
                snapshot,
                progress_callback=progress_callback,
            )
        finally:
            client.close()
            if target_db is not None:
                target_db.close()

    def _resolve_clone_target_local_db_path(self) -> str:
        """Return the file-backed local DB path for remote snapshot clones."""
        if self._db_path is not None:
            return self._db_path
        return DEFAULT_DB_PATH

    def _build_main_screen(self) -> MainScreen:
        """Build the main application screen."""
        screen = MainScreen(
            self._service,
            initial_select_pk=self._last_viewed_idea_pk,
            on_selected_idea_changed=self._on_selected_idea_changed,
            edit_body_cursor_mode=self._edit_body_cursor_mode,
            new_idea_group_mode=self._new_idea_group_mode,
            app_metadata=self._app_metadata,
        )
        screen.title = self.title
        return screen

    def _notify_invalid_config(self) -> None:
        """Warn when persisted config values are invalid."""
        if self._invalid_new_idea_group_mode:
            valid_values = ", ".join(
                f"'{value}'" for value in VALID_NEW_IDEA_GROUP_MODES
            )
            self.notify(
                "Invalid config "
                "'new_idea_group_mode="
                f"{self._configured_new_idea_group_mode}'; "
                "using 'contextual'. "
                f"Valid values: {valid_values}.",
                severity="warning",
            )

        if self._invalid_default_group_name:
            self.notify(
                "Invalid config "
                f"'default_group_name={self._configured_default_group_name}'; "
                f"using '{self._default_group_name}'.",
                severity="warning",
            )
        if self._invalid_data_backend_mode:
            self.notify(
                "Invalid config "
                "'data_backend_mode="
                f"{self._configured_data_backend_mode}'; "
                f"using '{self._data_backend_mode.value}'.",
                severity="warning",
            )
        if self._invalid_timezone:
            self.notify(
                "Invalid config "
                f"'timezone={self._configured_timezone}'; "
                "using system timezone.",
                severity="warning",
            )
        if self._invalid_date_format:
            valid_values = ", ".join(
                f"'{value}'" for value in VALID_DATE_FORMATS
            )
            self.notify(
                "Invalid config "
                f"'date_format={self._configured_date_format}'; "
                "using system locale. "
                f"Valid values: {valid_values}.",
                severity="warning",
            )

    def _on_selected_idea_changed(self, idea_pk: int | None) -> None:
        """Track currently selected idea for persistence."""
        self._last_viewed_idea_pk = idea_pk

    def exit(
        self,
        result: None = None,
        return_code: int = 0,
        message: RenderableType | None = None,
    ) -> None:
        """Persist settings before the app exits."""
        if isinstance(self.screen, MainScreen):
            self.screen.flush_idea_scroll_position()
        self._settings.last_viewed_idea_pk = self._last_viewed_idea_pk or 0
        self._settings.save()
        if isinstance(self._service, RemoteIdeaBackend):
            self._service.close()
        self._close_owned_db()
        super().exit(
            result=result,
            return_code=return_code,
            message=message,
        )

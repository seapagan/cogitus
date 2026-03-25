"""Cogitus Textual application."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import App

from cogitus.config import (
    VALID_NEW_IDEA_GROUP_MODES,
    get_settings,
    normalize_default_group_name,
    normalize_edit_body_cursor_mode,
    normalize_new_idea_group_mode,
)
from cogitus.db import get_db
from cogitus.metadata import get_app_metadata
from cogitus.repositories.group_repo import GroupRepository
from cogitus.services.idea_service import IdeaService
from cogitus.ui.screens.main_screen import MainScreen

if TYPE_CHECKING:
    from typing import Protocol

    from rich.console import RenderableType
    from sqliter import SqliterDB

    class SettingsLike(Protocol):
        """Settings interface required by the app."""

        last_viewed_idea_pk: int
        edit_body_cursor_mode: str
        new_idea_group_mode: str
        default_group_name: str

        def save(self) -> None:
            """Persist settings."""


CSS_PATH = Path(__file__).parent / "ui" / "styles" / "app.tcss"


class CogitusApp(App[None]):
    """Cogitus — a terminal workspace for programming ideas."""

    TITLE = "Cogitus"
    SUB_TITLE = "Idea Workspace"

    def __init__(
        self,
        db_path: str | None = None,
        db: SqliterDB | None = None,
        settings: SettingsLike | None = None,
    ) -> None:
        """Initialize the Cogitus application.

        Args:
            db_path: Path to the database file.
            db: Pre-configured database instance (for testing).
            settings: Optional settings instance (for testing).
        """
        super().__init__(css_path=CSS_PATH)
        self._app_metadata = get_app_metadata()
        self.title = self._app_metadata.title
        self.sub_title = self.SUB_TITLE
        self._settings = settings if settings is not None else get_settings()
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
        self._invalid_new_idea_group_mode = (
            configured_new_idea_mode != self._new_idea_group_mode.value
        )
        self._invalid_default_group_name = (
            not configured_default_group_name.strip()
        )
        last_viewed = self._settings.last_viewed_idea_pk
        self._last_viewed_idea_pk = last_viewed if last_viewed > 0 else None
        self._db = self._build_db(db_path=db_path, db=db)
        self._service = IdeaService(
            self._db,
            default_group_name=self._default_group_name,
        )

    def on_mount(self) -> None:
        """Push the main screen on mount."""
        self.push_screen(self._build_main_screen())
        self._notify_invalid_config()

    def _build_db(
        self,
        *,
        db_path: str | None,
        db: SqliterDB | None,
    ) -> SqliterDB:
        """Return the configured database instance."""
        if db is not None:
            GroupRepository(db).get_or_create(self._default_group_name)
            return db
        if db_path is not None:
            return get_db(
                db_path,
                default_group_name=self._default_group_name,
            )
        return get_db(default_group_name=self._default_group_name)

    def _build_main_screen(self) -> MainScreen:
        """Build the main application screen."""
        return MainScreen(
            self._service,
            initial_select_pk=self._last_viewed_idea_pk,
            on_selected_idea_changed=self._on_selected_idea_changed,
            edit_body_cursor_mode=self._edit_body_cursor_mode,
            new_idea_group_mode=self._new_idea_group_mode,
            app_metadata=self._app_metadata,
        )

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
        self._settings.last_viewed_idea_pk = self._last_viewed_idea_pk or 0
        self._settings.save()
        super().exit(
            result=result,
            return_code=return_code,
            message=message,
        )

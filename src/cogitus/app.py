"""Cogitus Textual application."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import App

from cogitus.config import (
    get_settings,
    normalize_edit_body_cursor_mode,
    normalize_new_idea_group_preselect_mode,
)
from cogitus.db import get_db
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
        new_idea_group_preselect_mode: str

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
        self._settings = settings if settings is not None else get_settings()
        self._edit_body_cursor_mode = normalize_edit_body_cursor_mode(
            self._settings.edit_body_cursor_mode
        )
        configured_new_idea_mode = self._settings.new_idea_group_preselect_mode
        self._configured_new_idea_group_preselect_mode = (
            configured_new_idea_mode
        )
        self._new_idea_group_preselect_mode = (
            normalize_new_idea_group_preselect_mode(configured_new_idea_mode)
        )
        self._invalid_new_idea_group_preselect_mode = (
            configured_new_idea_mode
            != self._new_idea_group_preselect_mode.value
        )
        last_viewed = self._settings.last_viewed_idea_pk
        self._last_viewed_idea_pk = last_viewed if last_viewed > 0 else None

        if db is not None:
            self._db = db
        elif db_path is not None:
            self._db = get_db(db_path)
        else:
            self._db = get_db()
        self._service = IdeaService(self._db)

    def on_mount(self) -> None:
        """Push the main screen on mount."""
        self.push_screen(
            MainScreen(
                self._service,
                initial_select_pk=self._last_viewed_idea_pk,
                on_selected_idea_changed=self._on_selected_idea_changed,
                edit_body_cursor_mode=self._edit_body_cursor_mode,
                new_idea_group_preselect_mode=(
                    self._new_idea_group_preselect_mode
                ),
            )
        )
        if self._invalid_new_idea_group_preselect_mode:
            self.notify(
                "Invalid config "
                "'new_idea_group_preselect_mode="
                f"{self._configured_new_idea_group_preselect_mode}'; "
                "using 'contextual'.",
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

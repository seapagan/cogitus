"""Cogitus Textual application."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import App

from cogitus.db import get_db
from cogitus.services.idea_service import IdeaService
from cogitus.ui.screens.main_screen import MainScreen

if TYPE_CHECKING:
    from sqliter import SqliterDB

CSS_PATH = Path(__file__).parent / "ui" / "styles" / "app.tcss"


class CogitusApp(App[None]):
    """Cogitus — a terminal workspace for programming ideas."""

    TITLE = "Cogitus"
    SUB_TITLE = "Idea Workspace"

    def __init__(
        self,
        db_path: str | None = None,
        db: SqliterDB | None = None,
    ) -> None:
        """Initialize the Cogitus application.

        Args:
            db_path: Path to the database file.
            db: Pre-configured database instance (for testing).
        """
        super().__init__(css_path=CSS_PATH)
        if db is not None:
            self._db = db
        elif db_path is not None:
            self._db = get_db(db_path)
        else:
            self._db = get_db()
        self._service = IdeaService(self._db)

    def on_mount(self) -> None:
        """Push the main screen on mount."""
        self.push_screen(MainScreen(self._service))

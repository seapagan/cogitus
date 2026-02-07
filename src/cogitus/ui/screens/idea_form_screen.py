"""Modal screens for idea create/edit, delete confirm, and help."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, TextArea

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from cogitus.models.idea import Idea
    from cogitus.services.idea_service import IdeaService


class IdeaFormScreen(ModalScreen[int | None]):
    """Modal form for creating or editing an idea."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding(
            "ctrl+s",
            "save",
            "Save",
            show=False,
            priority=True,
        ),
    ]

    def __init__(
        self,
        service: IdeaService,
        idea: Idea | None = None,
    ) -> None:
        """Initialize the idea form.

        Args:
            service: The IdeaService instance.
            idea: Existing idea to edit, or None for new.
        """
        super().__init__()
        self._service = service
        self._idea = idea

    def compose(self) -> ComposeResult:
        """Compose the idea form."""
        idea = self._idea
        is_edit = idea is not None
        form_title = "Edit Idea" if is_edit else "New Idea"

        with Vertical(id="idea-form-container"):
            yield Static(form_title, id="form-title")
            yield Label("Title")
            yield Input(
                value=idea.title if idea else "",
                placeholder="Idea title...",
                id="title-input",
            )
            yield Label("Body (Markdown)")
            yield TextArea(
                text=idea.body if idea else "",
                id="body-input",
                language="markdown",
            )
            yield Label("Tags (comma-separated)")
            yield Input(
                value=(self._get_existing_tags() if is_edit else ""),
                placeholder=("python, architecture, performance..."),
                id="tags-input",
            )
            with Horizontal(id="form-buttons"):
                yield Button(
                    "Save [Ctrl+S]",
                    variant="primary",
                    id="save-btn",
                )
                yield Button(
                    "Cancel [Esc]",
                    variant="default",
                    id="cancel-btn",
                )

    def _get_existing_tags(self) -> str:
        """Get comma-separated tags from the idea."""
        if self._idea is None:
            return ""
        tags = self._idea.tags.fetch_all()
        return ", ".join(t.name for t in tags)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "save-btn":
            self.action_save()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_save(self) -> None:
        """Save the idea."""
        title = self.query_one("#title-input", Input).value.strip()
        if not title:
            self.notify("Title is required", severity="error")
            self.query_one("#title-input", Input).focus()
            return

        body = self.query_one("#body-input", TextArea).text
        tags_str = self.query_one("#tags-input", Input).value
        tags = (
            [t.strip() for t in tags_str.split(",") if t.strip()]
            if tags_str.strip()
            else []
        )

        if self._idea is not None:
            result = self._service.update_idea(
                pk=self._idea.pk,
                title=title,
                body=body,
                tags=tags,
            )
            pk = result.pk if result else None
        else:
            idea = self._service.create_idea(
                title=title,
                body=body,
                tags=tags or None,
            )
            pk = idea.pk

        self.dismiss(pk)

    def action_cancel(self) -> None:
        """Cancel and dismiss."""
        self.dismiss(None)


class ConfirmDialog(ModalScreen[bool]):
    """Simple yes/no confirmation dialog."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("y", "confirm", "Yes", show=False),
        Binding("n", "cancel", "No", show=False),
    ]

    def __init__(self, message: str) -> None:
        """Initialize the confirmation dialog.

        Args:
            message: The confirmation message to display.
        """
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        """Compose the confirmation dialog."""
        with Vertical(id="confirm-container"):
            yield Static(self._message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button(
                    "Yes [Y]",
                    variant="error",
                    id="confirm-yes-btn",
                )
                yield Button(
                    "No [N]",
                    variant="default",
                    id="confirm-no-btn",
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "confirm-yes-btn":
            self.action_confirm()
        else:
            self.action_cancel()

    def action_confirm(self) -> None:
        """Confirm the action."""
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel the action."""
        self.dismiss(False)


class HelpScreen(ModalScreen[None]):
    """Help overlay showing keyboard shortcuts."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=False),
        Binding(
            "question_mark",
            "close",
            "Close",
            show=False,
        ),
    ]

    HELP_TEXT = (
        "[bold]Navigation[/bold]\n"
        "  Up/Down or j/k  Navigate ideas\n"
        "  Tab              Switch between panes\n"
        "  Enter            Select idea\n"
        "\n"
        "[bold]Actions[/bold]\n"
        "  n                New idea\n"
        "  e                Edit selected idea\n"
        "  d                Delete selected idea\n"
        "  /                Focus search\n"
        "  Escape           Clear search / close\n"
        "\n"
        "[bold]Form[/bold]\n"
        "  Ctrl+S           Save\n"
        "  Escape           Cancel\n"
        "\n"
        "[bold]General[/bold]\n"
        "  ?                Toggle this help\n"
        "  q                Quit"
    )

    def compose(self) -> ComposeResult:
        """Compose the help overlay."""
        with Vertical(id="help-container"):
            yield Static("Keyboard Shortcuts", id="help-title")
            with VerticalScroll(id="help-content"):
                yield Static(self.HELP_TEXT, markup=True)

    def action_close(self) -> None:
        """Close the help overlay."""
        self.dismiss(None)

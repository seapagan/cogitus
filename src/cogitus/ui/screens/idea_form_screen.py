"""Modal screens for idea create/edit, delete confirm, and help."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from cogitus.ui.widgets.text_area import CogitusTextArea

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
            with VerticalScroll(id="idea-form-scroll"):
                yield Label("Title")
                yield Input(
                    value=idea.title if idea else "",
                    placeholder="Idea title...",
                    id="title-input",
                )
                yield Label("Body (Markdown)")
                yield CogitusTextArea(
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
                yield Label("Group")
                yield Select[int](
                    options=self._group_options(),
                    value=self._get_existing_group_pk(),
                    allow_blank=False,
                    id="group-select",
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

    def _group_options(self) -> list[tuple[str, int]]:
        """Build Select options for available groups."""
        groups = self._service.list_groups()
        return [(group.name, group.pk) for group in groups]

    def _get_existing_group_pk(self) -> int:
        """Return current idea group pk for edit mode."""
        if self._idea is None:
            return self._get_default_group_pk()
        return self._idea.group.pk

    def _get_default_group_pk(self) -> int:
        """Return default group pk (fallback to first available group)."""
        groups = self._service.list_groups()
        for group in groups:
            if group.name == self._service.DEFAULT_GROUP_NAME:
                return group.pk
        return groups[0].pk

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

        body = self.query_one("#body-input", CogitusTextArea).text
        tags_str = self.query_one("#tags-input", Input).value
        group_value = self.query_one("#group-select", Select).value
        tags = (
            [t.strip() for t in tags_str.split(",") if t.strip()]
            if tags_str.strip()
            else []
        )
        group_pk = group_value if isinstance(group_value, int) else None

        if self._idea is not None:
            result = self._service.update_idea(
                pk=self._idea.pk,
                title=title,
                body=body,
                tags=tags,
                group_pk=group_pk,
            )
            pk = result.pk if result else None
        else:
            idea = self._service.create_idea(
                title=title,
                body=body,
                tags=tags or None,
                group_pk=group_pk,
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


class GroupFormScreen(ModalScreen[int | None]):
    """Modal form for creating a group."""

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

    def __init__(self, service: IdeaService) -> None:
        """Initialize the group form."""
        super().__init__()
        self._service = service

    def compose(self) -> ComposeResult:
        """Compose the group form."""
        with Vertical(id="confirm-container"):
            yield Static("New Group", id="form-title")
            yield Label("Name")
            yield Input(
                placeholder="Group name...",
                id="group-name-input",
            )
            with Horizontal(id="confirm-buttons"):
                yield Button(
                    "Save [Ctrl+S]",
                    variant="primary",
                    id="save-group-btn",
                )
                yield Button(
                    "Cancel [Esc]",
                    variant="default",
                    id="cancel-group-btn",
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "save-group-btn":
            self.action_save()
        elif event.button.id == "cancel-group-btn":
            self.action_cancel()

    def action_save(self) -> None:
        """Create the group and close."""
        name = self.query_one("#group-name-input", Input).value.strip()
        if not name:
            self.notify("Group name is required", severity="error")
            return
        try:
            group = self._service.create_group(name)
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        self.dismiss(group.pk)

    def action_cancel(self) -> None:
        """Cancel and dismiss."""
        self.dismiss(None)


class GroupDeleteReassignScreen(ModalScreen[int | None]):
    """Modal dialog to choose destination group when deleting a group."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("ctrl+s", "save", "Move+Delete", show=False, priority=True),
    ]

    def __init__(
        self,
        source_group_name: str,
        destination_options: list[tuple[str, int]],
    ) -> None:
        """Initialize with source and destination groups."""
        super().__init__()
        self._source_group_name = source_group_name
        self._destination_options = destination_options

    def compose(self) -> ComposeResult:
        """Compose the reassign modal."""
        with Vertical(id="confirm-container"):
            yield Static(
                f'Delete "{self._source_group_name}" and move ideas to:',
                id="confirm-message",
            )
            yield Select[int](
                options=self._destination_options,
                allow_blank=False,
                id="move-group-select",
            )
            with Horizontal(id="confirm-buttons"):
                yield Button(
                    "Move + Delete [Ctrl+S]",
                    variant="error",
                    id="move-delete-btn",
                )
                yield Button(
                    "Cancel [Esc]",
                    variant="default",
                    id="cancel-move-btn",
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "move-delete-btn":
            self.action_save()
        else:
            self.action_cancel()

    def action_save(self) -> None:
        """Return selected destination group pk."""
        value = self.query_one("#move-group-select", Select).value
        if not isinstance(value, int):
            self.notify("Select a destination group", severity="error")
            return
        self.dismiss(value)

    def action_cancel(self) -> None:
        """Cancel and dismiss."""
        self.dismiss(None)


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
        "  g                New group\n"
        "  G                Delete selected group\n"
        "  y                Copy idea body\n"
        "  /                Focus search\n"
        "  Escape           Clear search / close\n"
        "\n"
        "[bold]Form[/bold]\n"
        "  Ctrl+S           Save\n"
        "  y (selection)    Copy selected text\n"
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

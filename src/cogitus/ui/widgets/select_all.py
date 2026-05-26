"""Shared select-all handling for editable widgets."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Protocol

from textual.binding import Binding, BindingType
from textual.message import Message
from textual.widgets import Input

from cogitus.ui.widgets.text_area import CogitusTextArea

if TYPE_CHECKING:
    from textual.app import App
    from textual.events import Key
    from textual.geometry import Offset
    from textual.widget import Widget


class SelectAllInput(Input):
    """Input with explicit Ctrl+a/Ctrl+A select-all handling."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            "ctrl+a,ctrl+shift+a",
            "select_all",
            "Select All",
            show=False,
            priority=True,
        ),
    ]

    class SelectedAll(Message):
        """Posted when all input text is selected."""

        def __init__(self, input_widget: SelectAllInput) -> None:
            """Initialize with the input whose text was selected."""
            self.input = input_widget
            super().__init__()

        @property
        def control(self) -> SelectAllInput:
            """Alias for the input whose text was selected."""
            return self.input

    def action_select_all(self) -> None:
        """Select all input text."""
        self.select_all()
        self.post_message(self.SelectedAll(self))


class _FocusOwner(Protocol):
    """Object with access to a Textual app focus target."""

    app: App[object]


def handle_select_all_key(owner: _FocusOwner, event: Key) -> bool:
    """Handle Ctrl+a/Ctrl+A by selecting all text in the focused editor."""
    if event.key.lower() not in {"ctrl+a", "ctrl+shift+a"}:
        return False
    if not select_all_focused_text(owner):
        return False
    event.prevent_default()
    event.stop()
    return True


def select_all_focused_text(owner: _FocusOwner) -> bool:
    """Select all text in the owner's focused editable widget."""
    focused = owner.app.focused
    if focused is None:
        return False
    if focused.screen is not owner and owner not in focused.ancestors:
        return False
    return select_all_widget_text(focused)


def select_all_widget_text(widget: Widget) -> bool:
    """Select all text in a supported widget."""
    if isinstance(widget, CogitusTextArea):
        _select_all_text_area(widget)
        return True
    if isinstance(widget, Input):
        widget.select_all()
        return True
    return False


def _select_all_text_area(text_area: CogitusTextArea) -> None:
    """Select body text without moving the visible viewport."""
    scroll_offset: Offset = text_area.scroll_offset
    text_area.select_all()
    text_area.call_after_refresh(
        text_area.scroll_to,
        x=scroll_offset.x,
        y=scroll_offset.y,
        animate=False,
        immediate=True,
    )

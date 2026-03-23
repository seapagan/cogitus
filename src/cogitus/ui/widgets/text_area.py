"""Custom TextArea with clipboard integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import TextArea

from cogitus.ui.clipboard import copy_to_clipboard

if TYPE_CHECKING:
    from textual.events import Key


class CogitusTextArea(TextArea):
    """TextArea with custom clipboard and cursor-visibility behavior."""

    def on_key(self, event: Key) -> None:
        """Intercept custom key handling for the text area.

        When text is selected and 'y' is pressed, copies the
        selection to the system clipboard instead of inserting
        the character. When Enter inserts a new line at the bottom
        of the viewport, schedule a post-refresh scroll so the new
        cursor row is immediately visible.

        Args:
            event: The key event.
        """
        if event.key == "y" and self.selected_text:
            if copy_to_clipboard(self.selected_text, self.app):
                self.notify("Copied selection to clipboard")
            else:
                self.notify("Clipboard unavailable", severity="warning")
            event.prevent_default()
            event.stop()
            return

        if event.key == "enter":
            self.call_after_refresh(self.scroll_cursor_visible)

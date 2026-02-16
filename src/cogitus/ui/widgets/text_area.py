"""Custom TextArea with clipboard integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import TextArea

from cogitus.ui.clipboard import copy_to_clipboard

if TYPE_CHECKING:
    from textual.events import Key


class CogitusTextArea(TextArea):
    """TextArea that copies selected text on 'y' key press."""

    def on_key(self, event: Key) -> None:
        """Intercept 'y' to copy selected text to clipboard.

        When text is selected and 'y' is pressed, copies the
        selection to the system clipboard instead of inserting
        the character. Falls through to normal behavior otherwise.

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

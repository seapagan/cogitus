"""Clipboard utility for copying text to the system clipboard.

Uses two strategies for maximum coverage:
- OSC 52 escape sequence via Textual's App.copy_to_clipboard
  (works in modern terminals, through tmux, and over SSH)
- pyperclip as a silent fallback for terminals without OSC 52
  support (e.g. Gnome Terminal, macOS Terminal)
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import pyperclip

if TYPE_CHECKING:
    from textual.app import App


def copy_to_clipboard(text: str, app: App[object]) -> None:
    """Copy text to the system clipboard.

    Sends an OSC 52 escape sequence (handled by the terminal
    emulator) and also attempts a pyperclip copy as a fallback
    for terminals that do not support OSC 52.

    Args:
        text: The text to copy.
        app: The running Textual application instance.
    """
    app.copy_to_clipboard(text)
    with contextlib.suppress(pyperclip.PyperclipException):
        pyperclip.copy(text)

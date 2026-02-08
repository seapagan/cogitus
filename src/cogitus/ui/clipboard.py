"""Clipboard utility for copying text to the system clipboard."""

from __future__ import annotations

import pyperclip


def copy_to_clipboard(text: str) -> tuple[bool, str]:
    """Copy text to the system clipboard via pyperclip.

    Args:
        text: The text to copy.

    Returns:
        A (success, message) tuple.
    """
    try:
        pyperclip.copy(text)
    except pyperclip.PyperclipException as exc:
        return (False, str(exc))
    return (True, "Copied to clipboard")

"""Tests for the clipboard utility."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pyperclip
import pytest

from cogitus.ui.clipboard import copy_to_clipboard


class TestCopyToClipboard:
    """Tests for copy_to_clipboard."""

    @patch("cogitus.ui.clipboard.pyperclip.copy")
    def test_uses_osc52_and_pyperclip(self, mock_pyperclip: MagicMock) -> None:
        """Calls both OSC 52 and pyperclip."""
        mock_app: MagicMock = MagicMock()
        copy_to_clipboard("hello", mock_app)
        mock_app.copy_to_clipboard.assert_called_once_with("hello")
        mock_pyperclip.assert_called_once_with("hello")

    @patch("cogitus.ui.clipboard.pyperclip.copy")
    def test_pyperclip_failure_swallowed(
        self, mock_pyperclip: MagicMock
    ) -> None:
        """Silently swallows pyperclip exceptions."""
        mock_pyperclip.side_effect = pyperclip.PyperclipException(
            "no copy mechanism"
        )
        mock_app: MagicMock = MagicMock()
        copy_to_clipboard("hello", mock_app)
        mock_app.copy_to_clipboard.assert_called_once_with("hello")

    @patch("cogitus.ui.clipboard.pyperclip.copy")
    def test_empty_string(self, mock_pyperclip: MagicMock) -> None:
        """Handles copying an empty string."""
        mock_app: MagicMock = MagicMock()
        copy_to_clipboard("", mock_app)
        mock_app.copy_to_clipboard.assert_called_once_with("")
        mock_pyperclip.assert_called_once_with("")

    @patch("cogitus.ui.clipboard.pyperclip.copy")
    def test_app_copy_failure_still_uses_pyperclip(
        self, mock_pyperclip: MagicMock
    ) -> None:
        """Falls back to pyperclip when OSC 52 copy raises runtime/IO errors."""
        mock_app: MagicMock = MagicMock()
        mock_app.copy_to_clipboard.side_effect = OSError(
            "terminal write failed"
        )

        copy_to_clipboard("hello", mock_app)

        mock_app.copy_to_clipboard.assert_called_once_with("hello")
        mock_pyperclip.assert_called_once_with("hello")

    @patch("cogitus.ui.clipboard.pyperclip.copy")
    def test_unexpected_app_copy_failure_propagates(
        self, mock_pyperclip: MagicMock
    ) -> None:
        """Unexpected app-copy exceptions are not swallowed."""
        mock_app: MagicMock = MagicMock()
        mock_app.copy_to_clipboard.side_effect = ValueError("bad state")

        with pytest.raises(ValueError, match="bad state"):
            copy_to_clipboard("hello", mock_app)

        mock_pyperclip.assert_not_called()

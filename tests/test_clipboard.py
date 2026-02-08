"""Tests for the clipboard utility."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pyperclip

from cogitus.ui.clipboard import copy_to_clipboard


class TestCopyToClipboard:
    """Tests for copy_to_clipboard."""

    @patch("cogitus.ui.clipboard.pyperclip.copy")
    def test_uses_osc52_and_pyperclip(self, mock_pyperclip: MagicMock) -> None:
        """Calls both OSC 52 and pyperclip."""
        mock_app: MagicMock = MagicMock()
        assert copy_to_clipboard("hello", mock_app) is True
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
        assert copy_to_clipboard("hello", mock_app) is True
        mock_app.copy_to_clipboard.assert_called_once_with("hello")

    @patch("cogitus.ui.clipboard.pyperclip.copy")
    def test_empty_string(self, mock_pyperclip: MagicMock) -> None:
        """Handles copying an empty string."""
        mock_app: MagicMock = MagicMock()
        assert copy_to_clipboard("", mock_app) is True
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

        assert copy_to_clipboard("hello", mock_app) is True

        mock_app.copy_to_clipboard.assert_called_once_with("hello")
        mock_pyperclip.assert_called_once_with("hello")

    @patch("cogitus.ui.clipboard.pyperclip.copy")
    def test_both_clipboard_backends_fail(
        self, mock_pyperclip: MagicMock
    ) -> None:
        """Returns false when both clipboard backends fail."""
        mock_app: MagicMock = MagicMock()
        mock_app.copy_to_clipboard.side_effect = OSError(
            "terminal write failed"
        )
        mock_pyperclip.side_effect = pyperclip.PyperclipException(
            "no copy mechanism"
        )

        assert copy_to_clipboard("hello", mock_app) is False

        mock_pyperclip.assert_called_once_with("hello")

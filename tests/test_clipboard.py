"""Tests for the clipboard utility."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pyperclip

from cogitus.ui.clipboard import copy_to_clipboard


class TestCopyToClipboard:
    """Tests for copy_to_clipboard."""

    @patch("cogitus.ui.clipboard.pyperclip.copy")
    def test_success(self, mock_copy: MagicMock) -> None:
        """Returns success tuple when copy succeeds."""
        success, msg = copy_to_clipboard("hello")
        assert success is True
        assert "Copied" in msg
        mock_copy.assert_called_once_with("hello")

    @patch("cogitus.ui.clipboard.pyperclip.copy")
    def test_failure_no_clipboard_tool(self, mock_copy: MagicMock) -> None:
        """Returns failure tuple with the exception message."""
        mock_copy.side_effect = pyperclip.PyperclipException(
            "no copy mechanism"
        )
        success, msg = copy_to_clipboard("hello")
        assert success is False
        assert msg == "no copy mechanism"

    @patch("cogitus.ui.clipboard.pyperclip.copy")
    def test_empty_string(self, mock_copy: MagicMock) -> None:
        """Handles copying an empty string."""
        success, _msg = copy_to_clipboard("")
        assert success is True
        mock_copy.assert_called_once_with("")

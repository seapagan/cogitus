"""CLI package for Cogitus."""

from __future__ import annotations

import sys

from cogitus.cli.commands import app

__all__ = ["run_cli"]


def run_cli() -> None:
    """Run CLI commands if arguments are present.

    If no arguments are provided, returns to signal TUI should launch.
    Otherwise runs the CLI command (which calls sys.exit internally).
    """
    if len(sys.argv) == 1:
        # No arguments - return to signal TUI launch
        return
    # Run CLI - Typer calls sys.exit() internally
    app()

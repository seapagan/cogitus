"""CLI package for Cogitus."""

from __future__ import annotations

import sys

from cogitus.cli.commands import app

__all__ = ["run_cli"]


def run_cli() -> int | None:
    """Run CLI commands if arguments are present.

    Returns:
        None if TUI should be launched, otherwise an exit code.
    """
    if len(sys.argv) == 1:
        # No arguments - signal TUI launch
        return None
    # Run CLI and return 0 (typer handles its own exits on error)
    app()
    return 0

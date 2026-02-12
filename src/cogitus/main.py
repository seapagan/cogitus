"""CLI entrypoint for Cogitus."""

from cogitus.app import CogitusApp
from cogitus.cli import run_cli


def main() -> None:
    """Launch Cogitus - TUI or CLI based on arguments."""
    exit_code = run_cli()
    if exit_code is None:
        # No CLI args - launch TUI
        app = CogitusApp()
        app.run()
    else:
        raise SystemExit(exit_code)

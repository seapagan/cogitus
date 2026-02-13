"""CLI entrypoint for Cogitus."""

from cogitus.app import CogitusApp
from cogitus.cli import run_cli


def main() -> None:
    """Launch Cogitus - TUI or CLI based on arguments."""
    run_cli()  # Returns only if TUI should launch
    app = CogitusApp()
    app.run()

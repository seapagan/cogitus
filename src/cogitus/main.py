"""CLI entrypoint for Cogitus."""

from cogitus.app import CogitusApp


def main() -> None:
    """Launch the Cogitus TUI application."""
    app = CogitusApp()
    app.run()

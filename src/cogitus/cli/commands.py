"""Typer CLI commands for Cogitus."""

from __future__ import annotations

import os
from contextlib import contextmanager
from enum import Enum
from typing import TYPE_CHECKING, Annotated

import typer
import uvicorn

from cogitus.api.main import COGITUS_API_DB_PATH_ENV
from cogitus.cli.formatters import (
    format_idea_markdown,
    format_ideas_json,
    format_ideas_markdown,
    format_ideas_simple,
    format_ideas_table,
)
from cogitus.db import get_db
from cogitus.metadata import format_version_output, get_app_metadata
from cogitus.services.idea_service import IdeaService

if TYPE_CHECKING:
    from collections.abc import Generator


class ListFormat(str, Enum):
    """Valid output formats for list command."""

    simple = "simple"
    json = "json"
    table = "table"


class ExportFormat(str, Enum):
    """Valid output formats for export command."""

    json = "json"
    markdown = "markdown"


@contextmanager
def _db_session() -> Generator[IdeaService]:
    """Provide an IdeaService with automatic DB cleanup."""
    db = get_db()
    try:
        yield IdeaService(db)
    finally:
        db.close()


app = typer.Typer(
    name="cogitus",
    help="Cogitus — a terminal workspace for capturing and evolving ideas.",
    no_args_is_help=False,
    add_completion=False,
)
api_app = typer.Typer(help="Serve and manage the Cogitus API.")
app.add_typer(api_app, name="api")


def _version_callback(value: object) -> None:
    """Print the application version and exit."""
    if value is True:
        typer.echo(format_version_output(get_app_metadata()))
        raise typer.Exit


@app.callback(invoke_without_command=True)
def main(
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            expose_value=False,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
) -> None:
    """Define the top-level Typer callback for global CLI options.

    This callback exists to register options that apply to the root
    `cogitus` command, such as `--version`. Command dispatch is still
    handled by Typer; when `--version` is passed, `_version_callback`
    prints the version and exits before any subcommand runs.
    """


@app.command("list")
def cmd_list(
    query: Annotated[str | None, typer.Option("-q", "--query")] = None,
    output_format: Annotated[
        ListFormat, typer.Option("-f", "--format")
    ] = ListFormat.simple,
    limit: Annotated[int, typer.Option("-l", "--limit")] = 50,
) -> None:
    """List ideas with optional filtering.

    By default shows ideas in simple format. Use --format to change output.
    """
    with _db_session() as service:
        ideas = service.search_ideas(query) if query else service.list_ideas()
        ideas = ideas[:limit]

        if output_format == ListFormat.json:
            typer.echo(format_ideas_json(ideas))
        elif output_format == ListFormat.table:
            typer.echo(format_ideas_table(ideas))
        else:
            typer.echo(format_ideas_simple(ideas))


@app.command()
def export(
    pk: Annotated[int | None, typer.Argument()] = None,
    output_format: Annotated[
        ExportFormat, typer.Option("-f", "--format")
    ] = ExportFormat.json,
) -> None:
    """Export idea(s) to stdout.

    With no PK argument, exports all ideas. Use --format markdown for
    markdown output.
    """
    with _db_session() as service:
        if pk is not None:
            idea = service.get_idea_with_relations(pk)
            if idea is None:
                typer.secho(
                    f"Error: Idea {pk} not found.",
                    fg=typer.colors.RED,
                )
                raise typer.Exit(1)
            if output_format == ExportFormat.markdown:
                typer.echo(format_idea_markdown(idea))
            else:
                typer.echo(format_ideas_json([idea]))
        else:
            ideas = service.list_ideas()
            if output_format == ExportFormat.markdown:
                typer.echo(format_ideas_markdown(ideas))
            else:
                typer.echo(format_ideas_json(ideas))


@app.command()
def delete(
    pk: Annotated[int, typer.Argument()],
    force: Annotated[bool, typer.Option("-f", "--force")] = False,
) -> None:
    """Delete an idea by primary key.

    Prompts for confirmation unless --force is specified.
    """
    with _db_session() as service:
        idea = service.get_idea(pk)

        if idea is None:
            typer.secho(
                f"Error: Idea {pk} not found.",
                fg=typer.colors.RED,
            )
            raise typer.Exit(1)

        if not force and not typer.confirm(
            f"Delete idea '{idea.title}' (pk={pk})?",
            default=False,
        ):
            typer.echo("Aborted.")
            raise typer.Exit(0)

        service.delete_idea(pk)
        typer.secho(f"Deleted idea {pk}.", fg=typer.colors.GREEN)


@api_app.command("serve")
def serve_api(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8000,
    reload: Annotated[bool, typer.Option("--reload/--no-reload")] = False,
    db_path: Annotated[str | None, typer.Option("--db-path")] = None,
) -> None:
    """Serve the FastAPI application."""
    if db_path is None:
        os.environ.pop(COGITUS_API_DB_PATH_ENV, None)
    else:
        os.environ[COGITUS_API_DB_PATH_ENV] = db_path

    uvicorn.run(
        "cogitus.api.main:create_api_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )

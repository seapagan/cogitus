"""Typer CLI commands for Cogitus."""

from __future__ import annotations

from typing import Annotated

import typer

from cogitus.cli.formatters import (
    format_idea_markdown,
    format_ideas_json,
    format_ideas_markdown,
    format_ideas_simple,
    format_ideas_table,
)
from cogitus.db import get_db
from cogitus.services.idea_service import IdeaService

app = typer.Typer(
    name="cogitus",
    help="Cogitus — a terminal workspace for capturing and evolving ideas.",
    no_args_is_help=False,
)


@app.command("list")
def cmd_list(
    query: Annotated[str | None, typer.Option("-q", "--query")] = None,
    output_format: Annotated[str, typer.Option("-f", "--format")] = "simple",
    limit: Annotated[int, typer.Option("-l", "--limit")] = 50,
) -> None:
    """List ideas with optional filtering.

    By default shows ideas in simple format. Use --format to change output.
    """
    db = get_db()
    try:
        service = IdeaService(db)
        ideas = service.search_ideas(query) if query else service.list_ideas()

        # Apply limit
        ideas = ideas[:limit]

        if output_format == "json":
            typer.echo(format_ideas_json(ideas))
        elif output_format == "table":
            typer.echo(format_ideas_table(ideas))
        else:
            typer.echo(format_ideas_simple(ideas))
    finally:
        db.close()


@app.command()
def export(
    pk: Annotated[int | None, typer.Argument()] = None,
    output_format: Annotated[str, typer.Option("-f", "--format")] = "json",
) -> None:
    """Export idea(s) to stdout.

    With no PK argument, exports all ideas. Use --format markdown for
    markdown output.
    """
    db = get_db()
    try:
        service = IdeaService(db)

        if pk is not None:
            idea = service.get_idea(pk)
            if idea is None:
                typer.secho(
                    f"Error: Idea {pk} not found.",
                    fg=typer.colors.RED,
                )
                raise typer.Exit(1)
            if output_format == "markdown":
                typer.echo(format_idea_markdown(idea))
            else:
                typer.echo(format_ideas_json([idea]))
        else:
            ideas = service.list_ideas()
            if output_format == "markdown":
                typer.echo(format_ideas_markdown(ideas))
            else:
                typer.echo(format_ideas_json(ideas))
    finally:
        db.close()


@app.command()
def delete(
    pk: Annotated[int, typer.Argument()],
    force: Annotated[bool, typer.Option("-f", "--force")] = False,
) -> None:
    """Delete an idea by primary key.

    Prompts for confirmation unless --force is specified.
    """
    db = get_db()
    try:
        service = IdeaService(db)
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
    finally:
        db.close()

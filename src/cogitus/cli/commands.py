"""Typer CLI commands for Cogitus."""

from __future__ import annotations

import importlib
import os
from contextlib import contextmanager
from enum import Enum
from secrets import token_urlsafe
from typing import TYPE_CHECKING, Annotated, Protocol, cast

import typer

from cogitus.cli.formatters import (
    format_idea_markdown,
    format_ideas_json,
    format_ideas_markdown,
    format_ideas_simple,
    format_ideas_table,
)
from cogitus.config import get_settings, normalize_api_auth_username
from cogitus.db import get_db
from cogitus.metadata import format_version_output, get_app_metadata
from cogitus.services.idea_service import IdeaService

if TYPE_CHECKING:
    from collections.abc import Generator
    from types import ModuleType

COGITUS_API_DB_PATH_ENV = "COGITUS_API_DB_PATH"
COGITUS_MCP_DB_PATH_ENV = "COGITUS_MCP_DB_PATH"


class _UvicornModule(Protocol):
    """Protocol for the optional uvicorn module."""

    def run(
        self,
        app: str,
        *,
        host: str,
        port: int,
        reload: bool,
        factory: bool,
    ) -> None: ...


class _AuthModule(Protocol):
    """Protocol for the optional auth helper module."""

    def hash_password(self, password: str) -> str: ...


class _MCPAuthManagerProtocol(Protocol):
    """Protocol for the optional MCP auth manager."""

    def create_access_token(self) -> str: ...


class _MCPAuthManagerFactory(Protocol):
    """Protocol for constructing an optional MCP auth manager."""

    def __call__(self, settings: object) -> _MCPAuthManagerProtocol: ...


class _MCPAuthModule(Protocol):
    """Protocol for the optional MCP auth helper module."""

    MCPAuthManager: _MCPAuthManagerFactory


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
mcp_app = typer.Typer(help="Serve and manage the Cogitus MCP server.")
app.add_typer(api_app, name="api")
app.add_typer(mcp_app, name="mcp")


def _version_callback(value: object) -> None:
    """Print the application version and exit."""
    if value is True:
        typer.echo(format_version_output(get_app_metadata()))
        raise typer.Exit


def _import_optional_module(module_name: str) -> ModuleType:
    """Import an optional API dependency with a consistent error message."""
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        typer.secho(
            "The API server requires the optional 'api' extra. "
            "Install it with 'pip install cogitus[api]'.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1) from exc


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
    uvicorn = cast("_UvicornModule", _import_optional_module("uvicorn"))

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


@api_app.command("set-auth")
def set_api_auth(
    username: Annotated[str, typer.Option("--username", prompt=True)],
    password: Annotated[
        str,
        typer.Option(
            "--password",
            prompt=True,
            hide_input=True,
            confirmation_prompt=True,
        ),
    ],
    rotate_secret: Annotated[bool, typer.Option("--rotate-secret")] = False,
) -> None:
    """Configure or rotate the single-user API credentials."""
    auth_manager_module = cast(
        "_AuthModule",
        _import_optional_module("cogitus.api.managers.auth_manager"),
    )
    normalized_username = normalize_api_auth_username(username)
    if not normalized_username:
        typer.secho(
            "Error: username cannot be empty.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    settings = get_settings()
    settings.api_auth_username = normalized_username
    settings.api_auth_password_hash = auth_manager_module.hash_password(
        password
    )
    if rotate_secret or not settings.api_auth_jwt_secret.strip():
        settings.api_auth_jwt_secret = token_urlsafe(32)
    settings.save()

    typer.secho(
        f"Configured API auth for user '{normalized_username}'.",
        fg=typer.colors.GREEN,
    )
    if rotate_secret:
        typer.echo("JWT signing secret rotated.")


@mcp_app.command("token")
def create_mcp_token(
    rotate_secret: Annotated[bool, typer.Option("--rotate-secret")] = False,
) -> None:
    """Print a bearer token for MCP clients."""
    auth_manager_module = cast(
        "_MCPAuthModule",
        _import_optional_module("cogitus.api.managers.auth_manager"),
    )
    manager_factory = auth_manager_module.MCPAuthManager

    settings = get_settings()
    if rotate_secret or not settings.mcp_auth_jwt_secret.strip():
        settings.mcp_auth_jwt_secret = token_urlsafe(32)
        settings.save_mcp_auth_jwt_secret(settings.mcp_auth_jwt_secret)

    token = manager_factory(settings).create_access_token()
    typer.echo(f"Bearer {token}")
    if rotate_secret:
        typer.echo("Restart any running MCP servers to use the new secret.")


@mcp_app.command("serve")
def serve_mcp(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 9000,
    reload: Annotated[bool, typer.Option("--reload/--no-reload")] = False,
    db_path: Annotated[str | None, typer.Option("--db-path")] = None,
) -> None:
    """Serve the MCP-only FastAPI application."""
    uvicorn = cast("_UvicornModule", _import_optional_module("uvicorn"))
    settings = get_settings()
    if not settings.mcp_auth_jwt_secret.strip():
        typer.secho(
            "Error: MCP authentication is not configured. "
            "Run 'cogitus mcp token' first.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    _import_optional_module("cogitus.api.mcp")

    if db_path is None:
        os.environ.pop(COGITUS_MCP_DB_PATH_ENV, None)
    else:
        os.environ[COGITUS_MCP_DB_PATH_ENV] = db_path

    uvicorn.run(
        "cogitus.api.mcp:create_mcp_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )

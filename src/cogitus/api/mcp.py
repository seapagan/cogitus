"""MCP-only FastAPI application factory for Cogitus."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import httpx
from fastapi import FastAPI
from fastapi_mcp import FastApiMCP
from mcp.types import ToolAnnotations

from cogitus.api.dependencies import get_current_api_user, get_current_mcp_user
from cogitus.api.main import create_api_app
from cogitus.api.managers.auth_manager import MCPAuthManager
from cogitus.config import get_configured_mcp_auth_settings, get_settings
from cogitus.metadata import get_app_metadata

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

COGITUS_MCP_DB_PATH_ENV = "COGITUS_MCP_DB_PATH"
MCP_TOOL_OPERATION_IDS = (
    "get_idea_refs",
    "get_single_idea",
    "get_group_names",
    "get_tag_names",
)


def ensure_mcp_auth_configured() -> None:
    """Raise if MCP auth has not been configured."""
    settings = get_settings()
    MCPAuthManager(
        settings,
        get_configured_mcp_auth_settings(settings),
    ).ensure_configured()


def _mount_read_only_mcp_tools(
    *,
    internal_app: FastAPI,
    mcp_app: FastAPI,
    api_client: httpx.AsyncClient,
) -> None:
    """Mount the read-only MCP tools on the public MCP app."""
    mcp = FastApiMCP(
        internal_app,
        http_client=api_client,
        include_operations=list(MCP_TOOL_OPERATION_IDS),
    )

    for tool in mcp.tools:
        tool.annotations = ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    mcp.mount_http(mcp_app)


def create_mcp_app(
    *,
    db_path: str | None = None,
    memory: bool = False,
    default_group_name: str | None = None,
) -> FastAPI:
    """Create an MCP-only app exposing the Cogitus read-only tools."""
    ensure_mcp_auth_configured()
    resolved_db_path = db_path or os.getenv(COGITUS_MCP_DB_PATH_ENV)
    internal_app = create_api_app(
        db_path=resolved_db_path,
        memory=memory,
        default_group_name=default_group_name,
    )
    internal_app.dependency_overrides[get_current_api_user] = (
        get_current_mcp_user
    )
    api_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=internal_app,
            raise_app_exceptions=False,
        ),
        base_url="http://apiserver",
        timeout=10.0,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with internal_app.router.lifespan_context(internal_app):
            app.state.internal_api_app = internal_app
            app.state.mcp_api_client = api_client
            try:
                yield
            finally:
                await api_client.aclose()

    app_metadata = get_app_metadata()
    mcp_app = FastAPI(
        title=f"{app_metadata.title} MCP",
        version=app_metadata.version,
        summary="Cogitus MCP server.",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    _mount_read_only_mcp_tools(
        internal_app=internal_app,
        mcp_app=mcp_app,
        api_client=api_client,
    )
    return mcp_app

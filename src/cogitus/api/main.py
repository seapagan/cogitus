"""FastAPI application factory for Cogitus."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi_mcp import FastApiMCP
from mcp.types import ToolAnnotations

from cogitus.api.resources.auth import router as auth_router
from cogitus.api.resources.groups import router as groups_router
from cogitus.api.resources.ideas import router as ideas_router
from cogitus.api.resources.snapshot import router as snapshot_router
from cogitus.api.resources.tags import router as tags_router
from cogitus.config import get_settings
from cogitus.db import get_db
from cogitus.metadata import get_app_metadata
from cogitus.services.idea_service import IdeaService

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

COGITUS_API_DB_PATH_ENV = "COGITUS_API_DB_PATH"


def create_api_app(
    *,
    db_path: str | None = None,
    memory: bool = False,
    default_group_name: str | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    app_metadata = get_app_metadata()
    resolved_default_group_name = (
        get_settings().default_group_name
        if default_group_name is None
        else default_group_name
    )
    resolved_db_path = db_path or os.getenv(COGITUS_API_DB_PATH_ENV)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if memory:
            db = get_db(
                memory=True,
                default_group_name=resolved_default_group_name,
            )
        elif resolved_db_path is not None:
            db = get_db(
                db_path=resolved_db_path,
                default_group_name=resolved_default_group_name,
            )
        else:
            db = get_db(default_group_name=resolved_default_group_name)

        app.state.db = db
        app.state.idea_service = IdeaService(
            db,
            default_group_name=resolved_default_group_name,
        )
        try:
            yield
        finally:
            db.close()

    app = FastAPI(
        title=f"{app_metadata.title} API",
        version=app_metadata.version,
        summary=app_metadata.summary,
        lifespan=lifespan,
    )
    app.include_router(auth_router)
    app.include_router(ideas_router)
    app.include_router(groups_router)
    app.include_router(tags_router)
    app.include_router(snapshot_router)

    # add the mcp server
    mcp = FastApiMCP(
        app,
        include_operations=[
            "get_idea_refs",
            "get_single_idea",
            "get_group_names",
            "get_tag_names",
        ],
    )

    # set the correct annotations for each mcp tool.
    for tool in mcp.tools:
        tool.annotations = ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    mcp.mount_http()

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        """Return a simple health response."""
        return {"status": "ok"}

    return app

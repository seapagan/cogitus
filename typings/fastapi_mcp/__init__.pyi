from fastapi import APIRouter, FastAPI
from httpx import AsyncClient
from mcp.types import Tool

class AuthConfig: ...

class FastApiMCP:
    tools: list[Tool]

    def __init__(
        self,
        fastapi: FastAPI,
        name: str | None = ...,
        description: str | None = ...,
        describe_all_responses: bool = ...,
        describe_full_response_schema: bool = ...,
        http_client: AsyncClient | None = ...,
        include_operations: list[str] | None = ...,
        exclude_operations: list[str] | None = ...,
        include_tags: list[str] | None = ...,
        exclude_tags: list[str] | None = ...,
        auth_config: AuthConfig | None = ...,
        headers: list[str] = ...,
    ) -> None: ...
    def mount_http(
        self,
        router: FastAPI | APIRouter | None = ...,
        mount_path: str = ...,
    ) -> None: ...

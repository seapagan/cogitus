"""FastAPI routes for API authentication."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from cogitus.api.dependencies import get_auth_manager
from cogitus.api.managers.auth_manager import AuthManager
from cogitus.api.openapi_examples import (
    TOKEN_REQUEST_OPENAPI_EXAMPLES,
    TOKEN_RESPONSE_EXAMPLE,
    json_response_example,
)
from cogitus.api.schemas.response.auth import TokenResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/token",
    responses={
        status.HTTP_200_OK: json_response_example(TOKEN_RESPONSE_EXAMPLE),
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/x-www-form-urlencoded": {
                    "examples": TOKEN_REQUEST_OPENAPI_EXAMPLES,
                },
            },
        },
    },
)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> TokenResponse:
    """Authenticate the configured user and return a bearer token."""
    return manager.create_token_response(
        username=form_data.username,
        password=form_data.password,
    )

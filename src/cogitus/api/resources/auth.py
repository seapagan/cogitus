"""FastAPI routes for API authentication."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from cogitus.api.dependencies import get_auth_manager
from cogitus.api.managers.auth_manager import AuthManager
from cogitus.api.schemas.response.auth import TokenResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/token")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> TokenResponse:
    """Authenticate the configured user and return a bearer token."""
    return manager.create_token_response(
        username=form_data.username,
        password=form_data.password,
    )

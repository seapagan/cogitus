"""Response schemas for authentication."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class TokenResponse(BaseModel):
    """Bearer token response."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: Literal["bearer"]

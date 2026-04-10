"""Internal auth models for the API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class APIUser(BaseModel):
    """Authenticated API user."""

    model_config = ConfigDict(extra="forbid")

    username: str


class TokenPayload(BaseModel):
    """Decoded token payload data."""

    model_config = ConfigDict(extra="ignore")

    sub: str

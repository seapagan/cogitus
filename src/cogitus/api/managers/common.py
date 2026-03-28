"""Common manager helpers."""

from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException, status


def raise_not_found(resource_name: str, identifier: int) -> NoReturn:
    """Raise a standard 404 response for a missing resource."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource_name} {identifier} not found",
    )


def raise_http_for_value_error(error: ValueError) -> NoReturn:
    """Map service-layer validation errors to HTTP responses."""
    detail = str(error)
    lowered = detail.lower()

    if "not found" in lowered:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )
    if (
        "already exists" in lowered
        or "cannot be renamed" in lowered
        or "cannot be deleted" in lowered
        or "cannot move ideas" in lowered
        or "modified on the server" in lowered
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=detail,
    )

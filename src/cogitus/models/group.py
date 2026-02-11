"""Group model for organizing ideas."""

from __future__ import annotations

from typing import Annotated

from sqliter.model import unique
from sqliter.orm import BaseDBModel


class Group(BaseDBModel):
    """A named group that owns ideas."""

    name: Annotated[str, unique()]

    class Meta:
        """Metadata for the Group model."""

        table_name = "groups"

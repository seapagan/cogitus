"""Tag model for categorizing ideas."""

from __future__ import annotations

from typing import Annotated

from sqliter.model import unique
from sqliter.orm import BaseDBModel


class Tag(BaseDBModel):
    """A tag that can be associated with ideas."""

    name: Annotated[str, unique()]

    class Meta:
        """Metadata for the Tag model."""

        table_name = "tags"

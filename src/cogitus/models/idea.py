"""Idea model — the core entity of Cogitus."""

from __future__ import annotations

from typing import ClassVar

from sqliter.orm import BaseDBModel, ForeignKey, ManyToMany

from cogitus.models.group import Group
from cogitus.models.tag import Tag


class Idea(BaseDBModel):
    """A captured programming idea with optional body and tags."""

    title: str
    body: str = ""
    detail_hash: str = ""
    group: ForeignKey[Group] = ForeignKey(
        Group,
        related_name="ideas",
        on_delete="RESTRICT",
    )
    tags: ClassVar[ManyToMany[Tag]] = ManyToMany(Tag, related_name="ideas")

    class Meta:
        """Metadata for the Idea model."""

        table_name = "ideas"
        indexes: ClassVar[list[str]] = ["updated_at"]

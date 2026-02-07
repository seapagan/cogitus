"""Idea model — the core entity of Cogitus."""

from __future__ import annotations

from typing import ClassVar

from sqliter.orm import BaseDBModel, ManyToMany

from cogitus.models.tag import Tag


class Idea(BaseDBModel):
    """A captured programming idea with optional body and tags."""

    title: str
    body: str = ""
    tags: ClassVar[ManyToMany[Tag]] = ManyToMany(Tag, related_name="ideas")

    class Meta:
        """Metadata for the Idea model."""

        table_name = "ideas"
        indexes: ClassVar[list[str]] = ["updated_at"]

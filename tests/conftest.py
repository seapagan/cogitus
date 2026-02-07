"""Shared test fixtures for Cogitus."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqliter import SqliterDB

from cogitus.models.idea import Idea
from cogitus.models.tag import Tag
from cogitus.repositories.idea_repo import IdeaRepository
from cogitus.repositories.tag_repo import TagRepository
from cogitus.services.idea_service import IdeaService

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def db() -> Generator[SqliterDB]:
    """Provide a fresh in-memory database with tables."""
    database = SqliterDB(memory=True)
    database.create_table(Tag)
    database.create_table(Idea)
    yield database
    database.close()


@pytest.fixture
def tag_repo(db: SqliterDB) -> TagRepository:
    """Provide a TagRepository backed by in-memory db."""
    return TagRepository(db)


@pytest.fixture
def idea_repo(db: SqliterDB, tag_repo: TagRepository) -> IdeaRepository:
    """Provide an IdeaRepository backed by in-memory db."""
    return IdeaRepository(db, tag_repo)


@pytest.fixture
def service(db: SqliterDB) -> IdeaService:
    """Provide an IdeaService backed by in-memory db."""
    return IdeaService(db)


@pytest.fixture
def sample_ideas(service: IdeaService) -> list[Idea]:
    """Create a set of sample ideas for testing."""
    return [
        service.create_idea(
            "Python metaclasses",
            "Explore how metaclasses work in Python",
            ["python", "advanced"],
        ),
        service.create_idea(
            "REST API design",
            "Best practices for designing REST APIs",
            ["api", "architecture"],
        ),
        service.create_idea(
            "Async patterns",
            "Python async/await patterns and pitfalls",
            ["python", "async"],
        ),
    ]

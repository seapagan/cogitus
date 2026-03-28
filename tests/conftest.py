"""Shared test fixtures for Cogitus."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from cogitus.api.main import create_api_app
from cogitus.db import get_db
from cogitus.repositories.group_repo import GroupRepository
from cogitus.repositories.idea_cursor_state_repo import (
    IdeaCursorStateRepository,
)
from cogitus.repositories.idea_repo import IdeaRepository
from cogitus.repositories.tag_repo import TagRepository
from cogitus.services.idea_service import IdeaService

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqliter import SqliterDB

    from cogitus.models.idea import Idea


@pytest.fixture
def db() -> Generator[SqliterDB]:
    """Provide a fresh in-memory database with tables."""
    database = get_db(memory=True)
    yield database
    database.close()


@pytest.fixture
def tag_repo(db: SqliterDB) -> TagRepository:
    """Provide a TagRepository backed by in-memory db."""
    return TagRepository(db)


@pytest.fixture
def group_repo(db: SqliterDB) -> GroupRepository:
    """Provide a GroupRepository backed by in-memory db."""
    return GroupRepository(db)


@pytest.fixture
def idea_repo(
    db: SqliterDB,
    tag_repo: TagRepository,
    group_repo: GroupRepository,
) -> IdeaRepository:
    """Provide an IdeaRepository backed by in-memory db."""
    return IdeaRepository(db, tag_repo, group_repo)


@pytest.fixture
def idea_cursor_state_repo(db: SqliterDB) -> IdeaCursorStateRepository:
    """Provide IdeaCursorStateRepository backed by in-memory db."""
    return IdeaCursorStateRepository(db)


@pytest.fixture
def service(db: SqliterDB) -> IdeaService:
    """Provide an IdeaService backed by in-memory db."""
    return IdeaService(db)


@pytest.fixture
def api_client() -> Generator[TestClient]:
    """Provide a FastAPI test client backed by in-memory storage."""
    with TestClient(
        create_api_app(memory=True, default_group_name="default")
    ) as client:
        yield client


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

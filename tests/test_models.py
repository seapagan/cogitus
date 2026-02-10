"""Tests for data models."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqliter.exceptions import RecordInsertionError

from cogitus.models.group import Group
from cogitus.models.idea import Idea
from cogitus.models.tag import Tag

if TYPE_CHECKING:
    from sqliter import SqliterDB


@pytest.fixture
def default_group(db: SqliterDB) -> Group:
    """Return the default group created during DB initialization."""
    group = db.select(Group).filter(name="default").fetch_one()
    assert group is not None
    return group


class TestTagModel:
    """Tests for the Tag model."""

    def test_create_tag(self, db: SqliterDB) -> None:
        """Tag can be inserted and retrieved."""
        tag = db.insert(Tag(name="python"))
        assert tag.pk > 0
        assert tag.name == "python"

    def test_tag_has_timestamps(self, db: SqliterDB) -> None:
        """Tag gets auto-populated timestamps."""
        tag = db.insert(Tag(name="test"))
        assert tag.created_at > 0
        assert tag.updated_at > 0

    def test_tag_unique_name(self, db: SqliterDB) -> None:
        """Duplicate tag names are rejected."""
        db.insert(Tag(name="python"))
        with pytest.raises(RecordInsertionError):
            db.insert(Tag(name="python"))

    def test_tag_table_name(self) -> None:
        """Tag model uses correct table name."""
        assert Tag.get_table_name() == "tags"


class TestGroupModel:
    """Tests for the Group model."""

    def test_create_group(self, db: SqliterDB) -> None:
        """Group can be inserted and retrieved."""
        group = db.insert(Group(name="backend"))
        assert group.pk > 0
        assert group.name == "backend"

    def test_group_unique_name(self, db: SqliterDB) -> None:
        """Duplicate group names are rejected."""
        db.insert(Group(name="backend"))
        with pytest.raises(RecordInsertionError):
            db.insert(Group(name="backend"))

    def test_group_table_name(self) -> None:
        """Group model uses correct table name."""
        assert Group.get_table_name() == "groups"


class TestIdeaModel:
    """Tests for the Idea model."""

    def test_create_idea(self, db: SqliterDB, default_group: Group) -> None:
        """Idea can be inserted and retrieved."""
        idea = db.insert(Idea(title="Test idea", group=default_group))
        assert idea.pk > 0
        assert idea.title == "Test idea"
        assert idea.body == ""

    def test_idea_with_body(
        self,
        db: SqliterDB,
        default_group: Group,
    ) -> None:
        """Idea can be created with a body."""
        idea = db.insert(
            Idea(title="Test", body="Some body text", group=default_group)
        )
        assert idea.body == "Some body text"

    def test_idea_has_timestamps(
        self,
        db: SqliterDB,
        default_group: Group,
    ) -> None:
        """Idea gets auto-populated timestamps."""
        idea = db.insert(Idea(title="Test", group=default_group))
        assert idea.created_at > 0
        assert idea.updated_at > 0

    def test_idea_table_name(self) -> None:
        """Idea model uses correct table name."""
        assert Idea.get_table_name() == "ideas"

    def test_idea_tag_association(
        self,
        db: SqliterDB,
        default_group: Group,
    ) -> None:
        """Idea can have tags associated via M2M."""
        tag = db.insert(Tag(name="python"))
        idea = db.insert(Idea(title="Test", group=default_group))
        idea.tags.add(tag)

        tags = idea.tags.fetch_all()
        assert len(tags) == 1
        assert tags[0].name == "python"

    def test_idea_multiple_tags(
        self,
        db: SqliterDB,
        default_group: Group,
    ) -> None:
        """Idea can have multiple tags."""
        t1 = db.insert(Tag(name="python"))
        t2 = db.insert(Tag(name="testing"))
        idea = db.insert(Idea(title="Test", group=default_group))
        idea.tags.add(t1, t2)

        tags = idea.tags.fetch_all()
        assert len(tags) == 2
        tag_names = {t.name for t in tags}
        assert tag_names == {"python", "testing"}

    def test_idea_tag_reverse_relationship(
        self,
        db: SqliterDB,
        default_group: Group,
    ) -> None:
        """Tag can find its associated ideas."""
        tag = db.insert(Tag(name="python"))
        idea = db.insert(Idea(title="Test", group=default_group))
        idea.tags.add(tag)

        ideas = tag.ideas.fetch_all()  # type: ignore[attr-defined]
        assert len(ideas) == 1
        assert ideas[0].title == "Test"

"""Tests for repository layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqliter.exceptions import RecordInsertionError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from cogitus.repositories.group_repo import GroupRepository
    from cogitus.repositories.idea_repo import IdeaRepository
    from cogitus.repositories.tag_repo import TagRepository


class TestTagRepository:
    """Tests for TagRepository."""

    def test_get_or_create_new(self, tag_repo: TagRepository) -> None:
        """New tag is created if it does not exist."""
        tag = tag_repo.get_or_create("python")
        assert tag.name == "python"
        assert tag.pk > 0

    def test_get_or_create_existing(self, tag_repo: TagRepository) -> None:
        """Existing tag is returned without duplication."""
        t1 = tag_repo.get_or_create("python")
        t2 = tag_repo.get_or_create("python")
        assert t1.pk == t2.pk

    def test_get_or_create_normalizes(self, tag_repo: TagRepository) -> None:
        """Tag names are normalized on get_or_create."""
        t1 = tag_repo.get_or_create("Python")
        t2 = tag_repo.get_or_create("  PYTHON  ")
        assert t1.pk == t2.pk
        assert t1.name == "python"

    def test_find_by_name(self, tag_repo: TagRepository) -> None:
        """Tag is found by exact name match."""
        tag_repo.get_or_create("python")
        found = tag_repo.find_by_name("python")
        assert found is not None
        assert found.name == "python"

    def test_find_by_name_not_found(self, tag_repo: TagRepository) -> None:
        """None is returned for a missing tag name."""
        assert tag_repo.find_by_name("nonexistent") is None

    def test_list_all(self, tag_repo: TagRepository) -> None:
        """All tags are returned sorted by name."""
        tag_repo.get_or_create("zebra")
        tag_repo.get_or_create("alpha")
        tag_repo.get_or_create("middle")

        tags = tag_repo.list_all()
        assert len(tags) == 3
        assert [t.name for t in tags] == [
            "alpha",
            "middle",
            "zebra",
        ]

    def test_get_or_create_recovers_after_insert_race(
        self,
        tag_repo: TagRepository,
        mocker: MockerFixture,
    ) -> None:
        """Insert race should recover by re-fetching tag after insert error."""
        existing = tag_repo.get_or_create("python")

        find_mock = mocker.patch.object(
            tag_repo,
            "find_by_name",
            side_effect=[None, existing],
        )
        mocker.patch.object(
            tag_repo._db,
            "insert",
            side_effect=RecordInsertionError("insert failed"),
        )

        found = tag_repo.get_or_create("python")

        assert found.pk == existing.pk
        assert find_mock.call_count == 2


class TestIdeaRepository:
    """Tests for IdeaRepository."""

    def test_create_idea(self, idea_repo: IdeaRepository) -> None:
        """Idea is inserted with correct defaults."""
        idea = idea_repo.create("My idea")
        assert idea.pk > 0
        assert idea.title == "My idea"
        assert idea.body == ""
        assert idea.group.name == "default"

    def test_create_idea_with_body(self, idea_repo: IdeaRepository) -> None:
        """Idea is inserted with body text."""
        idea = idea_repo.create("My idea", body="Some body")
        assert idea.body == "Some body"

    def test_create_idea_with_tags(self, idea_repo: IdeaRepository) -> None:
        """Idea is inserted with associated tags."""
        idea = idea_repo.create("My idea", tag_names=["python", "testing"])
        tags = idea.tags.fetch_all()
        assert len(tags) == 2
        tag_names = {t.name for t in tags}
        assert tag_names == {"python", "testing"}

    def test_get_idea(self, idea_repo: IdeaRepository) -> None:
        """Idea is retrieved by primary key."""
        created = idea_repo.create("My idea")
        fetched = idea_repo.get(created.pk)
        assert fetched is not None
        assert fetched.title == "My idea"

    def test_get_idea_not_found(self, idea_repo: IdeaRepository) -> None:
        """None is returned for a missing primary key."""
        assert idea_repo.get(999) is None

    def test_list_all(self, idea_repo: IdeaRepository) -> None:
        """All ideas are returned ordered by updated_at."""
        idea_repo.create("First")
        idea_repo.create("Second")
        idea_repo.create("Third")

        ideas = idea_repo.list_all()
        assert len(ideas) == 3

    def test_list_all_with_limit(self, idea_repo: IdeaRepository) -> None:
        """Limit parameter restricts result count."""
        for i in range(5):
            idea_repo.create(f"Idea {i}")

        ideas = idea_repo.list_all(limit=2)
        assert len(ideas) == 2

    def test_update_idea(self, idea_repo: IdeaRepository) -> None:
        """Idea fields are modified by update."""
        created = idea_repo.create("Original")
        updated = idea_repo.update(created.pk, "Updated", "New body")
        assert updated is not None
        assert updated.title == "Updated"
        assert updated.body == "New body"

    def test_update_preserves_group_when_group_not_provided(
        self,
        idea_repo: IdeaRepository,
        group_repo: GroupRepository,
    ) -> None:
        """Update without group_pk should keep existing group assignment."""
        source = group_repo.create("source")
        created = idea_repo.create("Original", group_pk=source.pk)

        updated = idea_repo.update(created.pk, "Updated", "New body")

        assert updated is not None
        assert updated.group.pk == source.pk

    def test_update_idea_tags(self, idea_repo: IdeaRepository) -> None:
        """Tags are replaced by update."""
        created = idea_repo.create("Test", tag_names=["old"])
        idea_repo.update(created.pk, "Test", "", tag_names=["new"])
        fetched = idea_repo.get(created.pk)
        assert fetched is not None
        tags = fetched.tags.fetch_all()
        assert len(tags) == 1
        assert tags[0].name == "new"

    def test_update_nonexistent(self, idea_repo: IdeaRepository) -> None:
        """None is returned when updating a missing idea."""
        assert idea_repo.update(999, "X", "Y") is None

    def test_delete_idea(self, idea_repo: IdeaRepository) -> None:
        """Idea is removed by delete."""
        created = idea_repo.create("To delete")
        idea_repo.delete(created.pk)
        assert idea_repo.get(created.pk) is None

    def test_delete_removes_from_list(self, idea_repo: IdeaRepository) -> None:
        """Deleted idea no longer appears in list_all."""
        idea_repo.create("Keep")
        to_delete = idea_repo.create("Delete me")
        idea_repo.delete(to_delete.pk)

        ideas = idea_repo.list_all()
        assert len(ideas) == 1
        assert ideas[0].title == "Keep"

    def test_bulk_move_group(
        self,
        idea_repo: IdeaRepository,
        group_repo: GroupRepository,
    ) -> None:
        """Ideas can be bulk-moved between groups."""
        source = group_repo.create("source")
        target = group_repo.create("target")
        idea = idea_repo.create("Move me", group_pk=source.pk)

        moved_count = idea_repo.bulk_move_group(source.pk, target.pk)

        fetched = idea_repo.get(idea.pk)
        assert moved_count == 1
        assert fetched is not None
        assert fetched.group.pk == target.pk


class TestGroupRepository:
    """Tests for GroupRepository."""

    def test_create_and_find(self, group_repo: GroupRepository) -> None:
        """Group can be created and found by name."""
        group = group_repo.create("backend")
        found = group_repo.find_by_name("backend")
        assert group.pk > 0
        assert found is not None
        assert found.pk == group.pk

    def test_create_duplicate_raises(self, group_repo: GroupRepository) -> None:
        """Duplicate names are rejected."""
        group_repo.create("backend")
        with pytest.raises(ValueError, match="already exists"):
            group_repo.create("backend")

    def test_create_empty_name_raises(
        self,
        group_repo: GroupRepository,
    ) -> None:
        """Empty group names are rejected."""
        with pytest.raises(ValueError, match="cannot be empty"):
            group_repo.create("   ")

    def test_get_or_create_creates_when_missing(
        self, group_repo: GroupRepository
    ) -> None:
        """get_or_create should create a new group when none exists."""
        created = group_repo.get_or_create("new-group")
        assert created.name == "new-group"
        assert created.pk > 0

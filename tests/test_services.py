"""Tests for the service layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cogitus.services.idea_service import IdeaService


class TestIdeaService:
    """Tests for IdeaService."""

    def test_create_idea(self, service: IdeaService) -> None:
        """Idea is created and returned."""
        idea = service.create_idea("Test idea")
        assert idea.pk > 0
        assert idea.title == "Test idea"

    def test_create_idea_with_tags(self, service: IdeaService) -> None:
        """Idea is created with tags correctly."""
        idea = service.create_idea("Test", tags=["python", "testing"])
        tags = idea.tags.fetch_all()
        assert len(tags) == 2

    def test_tag_normalization(self, service: IdeaService) -> None:
        """Tags are normalized to lowercase and stripped."""
        idea = service.create_idea(
            "Test",
            tags=["  Python  ", "TESTING", "python"],
        )
        tags = idea.tags.fetch_all()
        tag_names = {t.name for t in tags}
        assert tag_names == {"python", "testing"}

    def test_empty_tags_filtered(self, service: IdeaService) -> None:
        """Empty tag strings are filtered out."""
        idea = service.create_idea("Test", tags=["python", "", "  "])
        tags = idea.tags.fetch_all()
        assert len(tags) == 1
        assert tags[0].name == "python"

    def test_update_idea(self, service: IdeaService) -> None:
        """Idea is modified by update."""
        idea = service.create_idea("Original")
        updated = service.update_idea(idea.pk, "Updated", "New body")
        assert updated is not None
        assert updated.title == "Updated"
        assert updated.body == "New body"

    def test_update_idea_not_found(self, service: IdeaService) -> None:
        """None is returned for a missing idea update."""
        assert service.update_idea(999, "X", "Y") is None

    def test_delete_idea(self, service: IdeaService) -> None:
        """Idea is removed by delete."""
        idea = service.create_idea("To delete")
        service.delete_idea(idea.pk)
        assert service.get_idea(idea.pk) is None

    def test_get_idea(self, service: IdeaService) -> None:
        """Idea is retrieved by primary key."""
        idea = service.create_idea("Test")
        fetched = service.get_idea(idea.pk)
        assert fetched is not None
        assert fetched.title == "Test"

    def test_get_idea_not_found(self, service: IdeaService) -> None:
        """None is returned for a missing primary key."""
        assert service.get_idea(999) is None

    def test_list_ideas(self, service: IdeaService) -> None:
        """All ideas are returned by list_ideas."""
        service.create_idea("First")
        service.create_idea("Second")
        ideas = service.list_ideas()
        assert len(ideas) == 2

    def test_list_tags(self, service: IdeaService) -> None:
        """All tags are returned alphabetically."""
        service.create_idea("A", tags=["zebra"])
        service.create_idea("B", tags=["alpha"])
        tags = service.list_tags()
        assert [t.name for t in tags] == [
            "alpha",
            "zebra",
        ]

    def test_none_tags_passthrough(self, service: IdeaService) -> None:
        """Passing None for tags leaves them unchanged."""
        idea = service.create_idea("Test", tags=["python"])
        updated = service.update_idea(idea.pk, "Test", "", tags=None)
        assert updated is not None
        tags = updated.tags.fetch_all()
        assert len(tags) == 1

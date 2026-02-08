"""Tests for the service layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from cogitus.services.idea_service import IdeaService


class TestIdeaService:
    """Tests for IdeaService."""

    def test_create_idea(self, service: IdeaService) -> None:
        """Idea is created and returned."""
        idea = service.create_idea("Test idea")
        assert idea.pk > 0
        assert idea.title == "Test idea"
        assert idea.group.name == "default"

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

    def test_create_and_list_groups(self, service: IdeaService) -> None:
        """Groups can be created and listed."""
        service.create_group("backend")
        names = [group.name for group in service.list_groups()]
        assert "default" in names
        assert "backend" in names

    def test_create_idea_in_selected_group(self, service: IdeaService) -> None:
        """Idea can be assigned to a selected group."""
        group = service.create_group("backend")
        idea = service.create_idea("Test", group_pk=group.pk)
        assert idea.group.pk == group.pk

    def test_update_idea_moves_group(self, service: IdeaService) -> None:
        """Existing idea can be moved between groups."""
        source = service.create_group("source")
        target = service.create_group("target")
        idea = service.create_idea("Test", group_pk=source.pk)
        updated = service.update_idea(
            idea.pk,
            "Test",
            "",
            group_pk=target.pk,
        )
        assert updated is not None
        assert updated.group.pk == target.pk

    def test_delete_group_moves_ideas(self, service: IdeaService) -> None:
        """Deleting a group moves ideas to destination group."""
        source = service.create_group("source")
        target = service.create_group("target")
        idea = service.create_idea("Test", group_pk=source.pk)

        service.delete_group(source.pk, move_to_group_pk=target.pk)

        moved = service.get_idea(idea.pk)
        assert moved is not None
        assert moved.group.pk == target.pk

    def test_default_group_cannot_be_deleted(
        self,
        service: IdeaService,
    ) -> None:
        """Default group cannot be deleted."""
        default = next(
            group
            for group in service.list_groups()
            if group.name == service.DEFAULT_GROUP_NAME
        )
        with pytest.raises(ValueError, match="cannot be deleted"):
            service.delete_group(default.pk)

    def test_none_tags_passthrough(self, service: IdeaService) -> None:
        """Passing None for tags leaves them unchanged."""
        idea = service.create_idea("Test", tags=["python"])
        updated = service.update_idea(idea.pk, "Test", "", tags=None)
        assert updated is not None
        tags = updated.tags.fetch_all()
        assert len(tags) == 1

    def test_list_ideas_grouped_filters_empty_groups_on_query(
        self,
        service: IdeaService,
    ) -> None:
        """Query mode should exclude groups with zero matching ideas."""
        backend = service.create_group("backend")
        service.create_idea("Matching idea", group_pk=backend.pk)
        service.create_group("empty-group")

        grouped = service.list_ideas_grouped("matching")
        names = [group.name for group, _ in grouped]

        assert "backend" in names
        assert "empty-group" not in names

    def test_delete_group_missing_group_noop(
        self,
        service: IdeaService,
    ) -> None:
        """Deleting a non-existent group should no-op."""
        service.delete_group(99999)

    def test_delete_group_target_missing_raises(
        self,
        service: IdeaService,
    ) -> None:
        """Deleting with a missing target should raise."""
        source = service.create_group("source")
        with pytest.raises(ValueError, match="Target group not found"):
            service.delete_group(source.pk, move_to_group_pk=99999)

    def test_delete_group_same_target_raises(
        self,
        service: IdeaService,
    ) -> None:
        """Deleting with source == target should raise."""
        source = service.create_group("source")
        with pytest.raises(
            ValueError,
            match="same group being deleted",
        ):
            service.delete_group(source.pk, move_to_group_pk=source.pk)

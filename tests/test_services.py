"""Tests for the service layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cogitus.services.idea_service import IdeaService

if TYPE_CHECKING:
    from pytest_mock import MockerFixture
    from sqliter import SqliterDB


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

    def test_rename_idea(self, service: IdeaService) -> None:
        """Idea rename should only update the title."""
        group = service.create_group("backend")
        idea = service.create_idea(
            "Original",
            body="Body text",
            group_pk=group.pk,
        )

        renamed = service.rename_idea(idea.pk, "Renamed")

        assert renamed is not None
        assert renamed.title == "Renamed"
        assert renamed.body == "Body text"
        assert renamed.group.pk == group.pk

    def test_rename_idea_not_found(self, service: IdeaService) -> None:
        """None is returned for a missing idea rename."""
        assert service.rename_idea(999, "Renamed") is None

    def test_rename_idea_preserves_validation_error(
        self,
        service: IdeaService,
        mocker: MockerFixture,
    ) -> None:
        """Repository validation errors should pass through unchanged."""
        mocker.patch.object(
            service._idea_repo,
            "rename",
            side_effect=ValueError("bad title"),
        )

        with pytest.raises(ValueError, match="bad title"):
            service.rename_idea(1, "Renamed")

    def test_rename_idea_normalizes_storage_error(
        self,
        service: IdeaService,
        mocker: MockerFixture,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Unexpected rename failures should become UI-safe ValueErrors."""
        mocker.patch.object(
            service._idea_repo,
            "rename",
            side_effect=RuntimeError("disk full"),
        )

        with (
            caplog.at_level("ERROR"),
            pytest.raises(ValueError, match="Failed to rename idea"),
        ):
            service.rename_idea(1, "Renamed")

        assert "Failed to rename idea pk=1" in caplog.text

    def test_delete_idea(self, service: IdeaService) -> None:
        """Idea is removed by delete."""
        idea = service.create_idea("To delete")
        service.set_idea_cursor_position(idea.pk, 5)
        service.delete_idea(idea.pk)
        assert service.get_idea(idea.pk) is None
        assert service.get_idea_cursor_position(idea.pk) is None

    def test_get_idea(self, service: IdeaService) -> None:
        """Idea is retrieved by primary key."""
        idea = service.create_idea("Test")
        fetched = service.get_idea(idea.pk)
        assert fetched is not None
        assert fetched.title == "Test"

    def test_get_idea_with_relations(self, service: IdeaService) -> None:
        """Idea relations should be available from eager-loading helper."""
        group = service.create_group("backend")
        idea = service.create_idea(
            "Test",
            tags=["python"],
            group_pk=group.pk,
        )

        fetched = service.get_idea_with_relations(idea.pk)

        assert fetched is not None
        assert fetched.group.pk == group.pk
        assert [tag.name for tag in fetched.tags.fetch_all()] == ["python"]

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

    def test_list_tags_in_use_excludes_orphans(
        self,
        service: IdeaService,
    ) -> None:
        """In-use tags should exclude tags no longer linked to ideas."""
        idea = service.create_idea("A", tags=["active", "stale"])
        updated = service.update_idea(
            idea.pk,
            "A",
            "",
            tags=["active"],
        )
        assert updated is not None

        assert [tag.name for tag in service.list_tags_in_use()] == ["active"]
        assert [tag.name for tag in service.list_tags()] == [
            "active",
            "stale",
        ]

    def test_list_tags_with_usage_includes_stale_counts(
        self,
        service: IdeaService,
    ) -> None:
        """Tag usage listing should include zero-count stale tags."""
        service.create_idea("A", tags=["alpha", "beta"])
        service.create_idea("B", tags=["alpha"])
        stale = service.create_idea("C", tags=["legacy"])
        service.update_idea(stale.pk, "C", "", tags=[])

        usage = {
            tag.name: count for tag, count in service.list_tags_with_usage()
        }
        assert usage["alpha"] == 2
        assert usage["beta"] == 1
        assert usage["legacy"] == 0

    def test_idea_cursor_position_roundtrip(
        self,
        service: IdeaService,
    ) -> None:
        """Cursor position should be persisted and retrieved by idea PK."""
        idea = service.create_idea("Cursor")
        assert service.get_idea_cursor_position(idea.pk) is None

        service.set_idea_cursor_position(idea.pk, 8)
        assert service.get_idea_cursor_position(idea.pk) == 8

    def test_create_and_list_groups(self, service: IdeaService) -> None:
        """Groups can be created and listed."""
        service.create_group("backend")
        names = [group.name for group in service.list_groups()]
        assert "default" in names
        assert "backend" in names

    def test_get_group(self, service: IdeaService) -> None:
        """Group should be retrievable by primary key."""
        group = service.create_group("backend")

        fetched = service.get_group(group.pk)

        assert fetched is not None
        assert fetched.pk == group.pk

    def test_get_group_not_found(self, service: IdeaService) -> None:
        """Missing groups should return None."""
        assert service.get_group(99999) is None

    def test_create_idea_in_selected_group(self, service: IdeaService) -> None:
        """Idea can be assigned to a selected group."""
        group = service.create_group("backend")
        idea = service.create_idea("Test", group_pk=group.pk)
        assert idea.group.pk == group.pk

    def test_rename_group(self, service: IdeaService) -> None:
        """Existing groups can be renamed."""
        group = service.create_group("backend")

        renamed = service.rename_group(group.pk, "FrontEnd")

        assert renamed is not None
        assert renamed.name == "frontend"

    def test_rename_group_missing_returns_none(
        self,
        service: IdeaService,
    ) -> None:
        """Missing groups should return None when renamed."""
        assert service.rename_group(99999, "backend") is None

    def test_rename_group_preserves_validation_error(
        self,
        service: IdeaService,
        mocker: MockerFixture,
    ) -> None:
        """Repository validation errors should pass through unchanged."""
        group = service.create_group("backend")
        mocker.patch.object(
            service._group_repo,
            "rename",
            side_effect=ValueError("already exists"),
        )

        with pytest.raises(ValueError, match="already exists"):
            service.rename_group(group.pk, "frontend")

    def test_rename_group_normalizes_storage_error(
        self,
        service: IdeaService,
        mocker: MockerFixture,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Unexpected group rename failures should become UI-safe errors."""
        group = service.create_group("backend")
        mocker.patch.object(
            service._group_repo,
            "rename",
            side_effect=RuntimeError("disk full"),
        )

        with (
            caplog.at_level("ERROR"),
            pytest.raises(ValueError, match="Failed to rename group"),
        ):
            service.rename_group(group.pk, "frontend")

        assert f"Failed to rename group pk={group.pk}" in caplog.text

    def test_default_group_cannot_be_renamed(
        self,
        service: IdeaService,
    ) -> None:
        """Default group should remain protected from rename."""
        default = next(
            group
            for group in service.list_groups()
            if group.name == service.default_group_name
        )

        with pytest.raises(ValueError, match="cannot be renamed"):
            service.rename_group(default.pk, "inbox")

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
            if group.name == service.default_group_name
        )
        with pytest.raises(ValueError, match="cannot be deleted"):
            service.delete_group(default.pk)

    def test_create_idea_uses_configured_default_group(
        self,
        db: SqliterDB,
    ) -> None:
        """Idea creation should use configured default group fallback."""
        custom = IdeaService(db, default_group_name="inbox")
        idea = custom.create_idea("Test")
        assert idea.group.name == "inbox"

    def test_configured_default_group_cannot_be_deleted(
        self,
        db: SqliterDB,
    ) -> None:
        """Configured fallback group should be protected from deletion."""
        custom = IdeaService(db, default_group_name="inbox")
        inbox = custom.create_group("inbox")
        with pytest.raises(ValueError, match="cannot be deleted"):
            custom.delete_group(inbox.pk)

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

    def test_list_ideas_grouped_filters_empty_groups_on_structured_query(
        self,
        service: IdeaService,
    ) -> None:
        """Structured query should also hide groups with no matches."""
        backend = service.create_group("backend")
        service.create_idea(
            "Matching idea",
            tags=["python"],
            group_pk=backend.pk,
        )
        service.create_group("empty-group")

        grouped = service.list_ideas_grouped("tag:python")
        names = [group.name for group, _ in grouped]

        assert "backend" in names
        assert "empty-group" not in names

    def test_list_search_results_grouped_skips_groups_without_matches(
        self,
        service: IdeaService,
    ) -> None:
        """Ranked search grouping should omit groups with zero results."""
        backend = service.create_group("backend")
        service.create_group("empty-group")
        service.create_idea("Matching idea", group_pk=backend.pk)

        grouped = service.list_search_results_grouped("matching")
        names = [group.name for group, _ in grouped]

        assert names == ["backend"]

    def test_search_ideas_advanced_aliases_search_behavior(
        self,
        service: IdeaService,
    ) -> None:
        """search_ideas should delegate to advanced parsed search."""
        service.create_idea("Python backend", tags=["python"])
        service.create_idea("Rust", tags=["rust"])

        basic = service.search_ideas("tag:python")
        advanced = service.search_ideas_advanced("tag:python")

        assert [idea.pk for idea in basic] == [idea.pk for idea in advanced]

    def test_has_ideas_in_group(self, service: IdeaService) -> None:
        """Group occupancy check should report true/false correctly."""
        backend = service.create_group("backend")
        empty = service.create_group("empty")
        service.create_idea("Idea", group_pk=backend.pk)

        assert service.has_ideas_in_group(backend.pk)
        assert not service.has_ideas_in_group(empty.pk)

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

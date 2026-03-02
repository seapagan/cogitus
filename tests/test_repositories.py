"""Tests for repository layer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from sqliter.exceptions import RecordInsertionError

from cogitus.models import Idea
from cogitus.repositories.idea_repo import IdeaRepository
from cogitus.search import SearchFilter
from cogitus.search.result import SearchMatchFragment

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from cogitus.repositories.group_repo import GroupRepository
    from cogitus.repositories.idea_cursor_state_repo import (
        IdeaCursorStateRepository,
    )
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

    def test_create_with_missing_group_raises(
        self,
        idea_repo: IdeaRepository,
    ) -> None:
        """Explicitly invalid group IDs should raise."""
        with pytest.raises(ValueError, match="not found"):
            idea_repo.create("Bad group", group_pk=99999)

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

    def test_get_with_relations_loads_group_and_tags(
        self,
        idea_repo: IdeaRepository,
        group_repo: GroupRepository,
    ) -> None:
        """get_with_relations should return group and tags."""
        source = group_repo.create("source")
        created = idea_repo.create(
            "Idea with relations",
            body="body",
            tag_names=["python"],
            group_pk=source.pk,
        )

        fetched = idea_repo.get_with_relations(created.pk)

        assert fetched is not None
        assert fetched.group.pk == source.pk
        assert [tag.name for tag in fetched.tags.fetch_all()] == ["python"]

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

    def test_update_with_missing_group_raises(
        self,
        idea_repo: IdeaRepository,
    ) -> None:
        """Explicitly invalid group IDs should raise."""
        created = idea_repo.create("Test")
        with pytest.raises(ValueError, match="not found"):
            idea_repo.update(
                created.pk,
                "Updated",
                "Body",
                group_pk=99999,
            )

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

    def test_delete_removes_db_row_before_search_index(
        self,
        idea_repo: IdeaRepository,
        mocker: MockerFixture,
    ) -> None:
        """Delete should remove the canonical row before the FTS entry."""
        created = idea_repo.create("Delete ordering")
        calls: list[str] = []

        delete_mock = mocker.patch.object(
            idea_repo._db,
            "delete",
            autospec=True,
            side_effect=lambda model, pk: calls.append(
                f"db:{model.__name__}:{pk}"
            ),
        )
        search_delete_mock = mocker.patch.object(
            idea_repo._search_backend,
            "delete_idea",
            autospec=True,
            side_effect=lambda pk: calls.append(f"fts:{pk}"),
        )

        idea_repo.delete(created.pk)

        delete_mock.assert_called_once_with(Idea, created.pk)
        search_delete_mock.assert_called_once_with(created.pk)
        assert calls == [
            f"db:Idea:{created.pk}",
            f"fts:{created.pk}",
        ]

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

    def test_bulk_move_group_noop_for_same_group(
        self,
        idea_repo: IdeaRepository,
        group_repo: GroupRepository,
    ) -> None:
        """Bulk move should no-op when source and target groups are same."""
        source = group_repo.create("source")
        idea = idea_repo.create("Stay put", group_pk=source.pk)
        moved_count = idea_repo.bulk_move_group(source.pk, source.pk)

        fetched = idea_repo.get(idea.pk)
        assert moved_count == 0
        assert fetched is not None
        assert fetched.group.pk == source.pk

    def test_has_for_group(
        self,
        idea_repo: IdeaRepository,
        group_repo: GroupRepository,
    ) -> None:
        """has_for_group should return true only when group has ideas."""
        source = group_repo.create("source")
        empty = group_repo.create("empty")
        idea_repo.create("In source", group_pk=source.pk)

        assert idea_repo.has_for_group(source.pk)
        assert not idea_repo.has_for_group(empty.pk)

    def test_list_for_group(
        self,
        idea_repo: IdeaRepository,
        group_repo: GroupRepository,
    ) -> None:
        """list_for_group should return only ideas for selected group."""
        source = group_repo.create("source")
        other = group_repo.create("other")
        source_idea = idea_repo.create("In source", group_pk=source.pk)
        idea_repo.create("In other", group_pk=other.pk)

        ideas = idea_repo.list_for_group(source.pk)

        assert len(ideas) == 1
        assert ideas[0].pk == source_idea.pk

    def test_search_tag_matches_include_group_relations(
        self,
        idea_repo: IdeaRepository,
        group_repo: GroupRepository,
    ) -> None:
        """Tag-only matches should still return ideas with group loaded."""
        source = group_repo.create("source")
        created = idea_repo.create(
            "No query text in title",
            body="No query text in body",
            tag_names=["needle"],
            group_pk=source.pk,
        )

        results = idea_repo.search("needle")

        assert [idea.pk for idea in results] == [created.pk]
        assert results[0].group.pk == source.pk

    def test_search_structured_group_and_tag_filters(
        self,
        idea_repo: IdeaRepository,
        group_repo: GroupRepository,
    ) -> None:
        """Structured group/tag filters should intersect correctly."""
        backend = group_repo.create("backend")
        other = group_repo.create("other")
        wanted = idea_repo.create(
            "Wanted",
            tag_names=["python"],
            group_pk=backend.pk,
        )
        idea_repo.create("Wrong group", tag_names=["python"], group_pk=other.pk)
        idea_repo.create("Wrong tag", tag_names=["rust"], group_pk=backend.pk)

        results = idea_repo.search("group:backend and tag:python")

        assert [idea.pk for idea in results] == [wanted.pk]

    def test_search_structured_filters_support_or(
        self,
        idea_repo: IdeaRepository,
    ) -> None:
        """OR connector should union structured filter result sets."""
        first = idea_repo.create("First", tag_names=["python"])
        second = idea_repo.create("Second", tag_names=["api"])
        idea_repo.create("Third", tag_names=["rust"])

        results = idea_repo.search("tag:python or tag:api")
        found = {idea.pk for idea in results}

        assert found == {first.pk, second.pk}

    def test_search_structured_filters_left_to_right_evaluation(
        self,
        idea_repo: IdeaRepository,
    ) -> None:
        """Structured connectors should fold left-to-right."""
        idea_repo.create("A", tag_names=["a"])
        idea_repo.create("B", tag_names=["b"])
        ac = idea_repo.create("AC", tag_names=["a", "c"])
        bc = idea_repo.create("BC", tag_names=["b", "c"])

        results = idea_repo.search("tag:a or tag:b and tag:c")

        assert {idea.pk for idea in results} == {ac.pk, bc.pk}

    def test_search_invalid_operator_fragments_degrade_to_text(
        self,
        idea_repo: IdeaRepository,
    ) -> None:
        """Invalid operator fragments should behave like plain text."""
        expected = idea_repo.create("tag: marker")
        idea_repo.create("ordinary")

        results = idea_repo.search("tag:")

        assert [idea.pk for idea in results] == [expected.pk]

    def test_combine_match_sets_returns_empty_for_none_inputs(
        self,
        idea_repo: IdeaRepository,
    ) -> None:
        """Combining with no text/filter matches should yield an empty set."""
        assert idea_repo._combine_match_sets(None, None) == set()

    def test_matching_pks_for_text_empty_query_returns_empty_set(
        self,
        idea_repo: IdeaRepository,
    ) -> None:
        """Blank text query should return no direct text matches."""
        assert idea_repo._matching_pks_for_text("   ") == set()

    def test_matching_pks_for_filters_empty_filters_returns_empty_set(
        self,
        idea_repo: IdeaRepository,
    ) -> None:
        """No structured filters should return an empty folded set."""
        assert idea_repo._matching_pks_for_filters((), ()) == set()

    def test_matching_pks_for_tag_missing_tag_returns_empty_set(
        self,
        idea_repo: IdeaRepository,
    ) -> None:
        """Unknown tag filter should return no matching idea PKs."""
        assert idea_repo._matching_pks_for_tag("missing") == set()

    def test_matching_pks_for_group_missing_group_returns_empty_set(
        self,
        idea_repo: IdeaRepository,
    ) -> None:
        """Unknown group filter should return no matching idea PKs."""
        assert idea_repo._matching_pks_for_group("missing") == set()

    def test_matching_pks_for_filter_rejects_unsupported_field(
        self,
        idea_repo: IdeaRepository,
    ) -> None:
        """Unexpected filter fields should fail loudly."""
        invalid_field: Any = "status"
        invalid = SearchFilter(field=invalid_field, value="python")

        with pytest.raises(ValueError, match="Unsupported filter field"):
            idea_repo._matching_pks_for_filter(invalid)

    def test_legacy_text_matches_cover_body_only_and_tag_matches(
        self,
        idea_repo: IdeaRepository,
    ) -> None:
        """Legacy fallback should still match title, body, and tag-only text."""
        title_match = idea_repo.create(
            "Title fallback marker",
            body="",
        )
        body_match = idea_repo.create(
            "No punctuation in title",
            body="Body-only fallback for body? queries",
        )
        tag_match = idea_repo.create(
            "Tag fallback",
            body="",
            tag_names=["c++"],
        )

        title_results = idea_repo._legacy_text_matches("marker")
        body_results = idea_repo._legacy_text_matches("body?")
        tag_results = idea_repo._legacy_text_matches("c++")

        assert title_match.pk in title_results
        assert body_results[body_match.pk][1] is not None
        assert tag_match.pk in tag_results

    def test_legacy_snippet_and_window_cover_fallback_branches(
        self,
        idea_repo: IdeaRepository,
    ) -> None:
        """Legacy snippet helpers should cover title/body fallback branches."""
        title_only = idea_repo.create(
            "Title has python",
            body="no match here",
        )
        body_fallback = idea_repo.create(
            "Fallback title",
            body="Body text without the requested token but with content",
        )
        empty = idea_repo.create("", body=" \n ")

        assert (
            IdeaRepository._legacy_snippet(title_only, "python")
            == "Title has python"
        )
        assert (
            IdeaRepository._legacy_snippet(body_fallback, "missing")
            == "Body text without the requested token but with content"
        )
        assert IdeaRepository._legacy_snippet(empty, "missing") is None

        assert IdeaRepository._snippet_window(" \n ", "python") == ""
        assert (
            IdeaRepository._snippet_window(
                "Body text without the requested token but with content",
                "missing",
            )
            == "Body text without the requested token but with content"
        )

        long_text = "prefix words " * 8 + "python target " + "suffix words " * 8
        highlighted = IdeaRepository._snippet_window(long_text, "python")
        assert highlighted.startswith("...")
        assert "python target" in highlighted
        assert highlighted.endswith("...")

    def test_legacy_text_matches_skip_body_when_snippet_builder_returns_none(
        self,
        idea_repo: IdeaRepository,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Legacy body branch should skip entries when snippet build fails."""
        idea_repo.create(
            "No title punctuation",
            body="Body-only fallback for body? queries",
        )
        monkeypatch.setattr(idea_repo, "_legacy_snippet", lambda *_args: None)

        assert idea_repo._legacy_text_matches("body?") == {}

    def test_fragment_helpers_cover_group_dedupe_and_fallback_paths(
        self,
        idea_repo: IdeaRepository,
        group_repo: GroupRepository,
    ) -> None:
        """Fragment helpers should cover group mismatch and dedupe branches."""
        backend = group_repo.create("backend")
        idea = idea_repo.create(
            "Grouped python",
            group_pk=backend.pk,
            tag_names=["python"],
        )

        assert idea_repo._filter_match_fragments(
            idea,
            (
                SearchFilter(field="group", value="frontend"),
                SearchFilter(field="tag", value="python"),
                SearchFilter(field="tag", value="python"),
            ),
        ) == (
            SearchMatchFragment(
                source="tag",
                text="Tag: [[python]]",
                rank=50,
                is_synthetic=True,
            ),
        )

        assert (
            idea_repo._mark_legacy_match("plain text", "missing")
            == "plain text"
        )
        assert idea_repo._snippet_from_fragments(()) is None


class TestIdeaCursorStateRepository:
    """Tests for IdeaCursorStateRepository."""

    def test_get_position_returns_none_when_missing(
        self,
        idea_cursor_state_repo: IdeaCursorStateRepository,
    ) -> None:
        """Missing cursor state should return None."""
        assert idea_cursor_state_repo.get_position(12345) is None

    def test_set_position_creates_and_updates(
        self,
        idea_cursor_state_repo: IdeaCursorStateRepository,
        idea_repo: IdeaRepository,
    ) -> None:
        """set_position should create and then update existing state."""
        idea = idea_repo.create("Cursor")
        idea_cursor_state_repo.set_position(idea.pk, 3)
        assert idea_cursor_state_repo.get_position(idea.pk) == 3

        idea_cursor_state_repo.set_position(idea.pk, 7)
        assert idea_cursor_state_repo.get_position(idea.pk) == 7

    def test_set_position_clamps_negative_values(
        self,
        idea_cursor_state_repo: IdeaCursorStateRepository,
        idea_repo: IdeaRepository,
    ) -> None:
        """Negative cursor positions should be clamped to zero."""
        idea = idea_repo.create("Cursor")
        idea_cursor_state_repo.set_position(idea.pk, -10)
        assert idea_cursor_state_repo.get_position(idea.pk) == 0

    def test_set_position_missing_idea_noop(
        self,
        idea_cursor_state_repo: IdeaCursorStateRepository,
    ) -> None:
        """Missing idea should no-op when setting cursor position."""
        idea_cursor_state_repo.set_position(99999, 4)
        assert idea_cursor_state_repo.get_position(99999) is None


class TestGroupRepository:
    """Tests for GroupRepository."""

    def test_create_and_find(self, group_repo: GroupRepository) -> None:
        """Group can be created and found by name."""
        group = group_repo.create("BackEnd")
        found = group_repo.find_by_name("backend")
        assert group.pk > 0
        assert group.name == "backend"
        assert found is not None
        assert found.pk == group.pk

    def test_create_duplicate_raises(self, group_repo: GroupRepository) -> None:
        """Duplicate names are rejected."""
        group_repo.create("backend")
        with pytest.raises(ValueError, match="already exists"):
            group_repo.create("BackEnd")

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
        created = group_repo.get_or_create("New-Group")
        assert created.name == "new-group"
        assert created.pk > 0

    def test_get_or_create_recovers_after_insert_race(
        self,
        group_repo: GroupRepository,
        mocker: MockerFixture,
    ) -> None:
        """Insert race should recover by re-fetching after create error."""
        existing = group_repo.create("backend")
        find_mock = mocker.patch.object(
            group_repo,
            "find_by_name",
            side_effect=[None, existing],
        )
        mocker.patch.object(
            group_repo,
            "create",
            side_effect=ValueError("already exists"),
        )

        found = group_repo.get_or_create("backend")

        assert found.pk == existing.pk
        assert find_mock.call_count == 2

    def test_get_or_create_reraises_when_refetch_still_missing(
        self,
        group_repo: GroupRepository,
        mocker: MockerFixture,
    ) -> None:
        """Create errors are re-raised if race-recovery refetch still fails."""
        mocker.patch.object(
            group_repo,
            "find_by_name",
            side_effect=[None, None],
        )
        mocker.patch.object(
            group_repo,
            "create",
            side_effect=ValueError("already exists"),
        )

        with pytest.raises(ValueError, match="already exists"):
            group_repo.get_or_create("backend")

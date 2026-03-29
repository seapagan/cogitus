"""Tests for repository layer."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from sqliter.exceptions import RecordInsertionError, RecordUpdateError

from cogitus.models import Idea, Tag
from cogitus.repositories import tag_repo as tag_repo_module
from cogitus.repositories.idea_repo import IdeaRepository
from cogitus.search import SearchFilter, parse_search_query
from cogitus.search.backend import FtsSearchMatch
from cogitus.search.result import SearchMatchFragment

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from cogitus.repositories.group_repo import GroupRepository
    from cogitus.repositories.idea_cursor_state_repo import (
        IdeaCursorStateRepository,
    )
    from cogitus.repositories.tag_repo import TagRepository


def _seed_tag_usage_data(
    tag_repo: TagRepository,
    idea_repo: IdeaRepository,
) -> None:
    """Seed tags and ideas for tag usage repository tests."""
    tag_repo.get_or_create("unused")
    idea_repo.create("First idea", tag_names=["python", "testing"])
    idea_repo.create("Second idea", tag_names=["python"])


class _FakeTagUsageQuery:
    """Minimal query stub for list_with_usage() projection tests."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        """Store the rows returned by fetch_dicts()."""
        self._rows = rows

    def with_count(
        self,
        path: str,
        alias: str = "count",
    ) -> _FakeTagUsageQuery:
        """Return self after verifying the expected aggregation call."""
        assert path == Idea.tags.related_name
        assert alias == "usage"
        return self

    def order(
        self,
        order_by_field: str | None = None,
    ) -> _FakeTagUsageQuery:
        """Return self after verifying ordering."""
        assert order_by_field == "name"
        return self

    def fetch_dicts(self) -> list[dict[str, object]]:
        """Return the configured projection rows."""
        return self._rows


class TestTagRepository:
    """Tests for TagRepository."""

    def test_get_or_create_new(self, tag_repo: TagRepository) -> None:
        """New tag is created if it does not exist."""
        tag = tag_repo.get_or_create("python")
        assert tag.name == "python"
        assert tag.pk > 0

    def test_create_tag_rejects_empty_name(
        self,
        tag_repo: TagRepository,
    ) -> None:
        """Creating a tag with an empty name should fail."""
        with pytest.raises(ValueError, match="cannot be empty"):
            tag_repo.create("   ")

    def test_create_tag_rejects_duplicate_name(
        self,
        tag_repo: TagRepository,
    ) -> None:
        """Creating a duplicate tag should fail clearly."""
        tag_repo.create("python")

        with pytest.raises(ValueError, match='Tag "python" already exists'):
            tag_repo.create("Python")

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

    def test_rename_tag_updates_name(self, tag_repo: TagRepository) -> None:
        """Renaming a tag should normalize and persist the new name."""
        tag = tag_repo.create("python")

        renamed = tag_repo.rename(tag.pk, "FastAPI")

        assert renamed is not None
        assert renamed.name == "fastapi"
        assert tag_repo.find_by_name("fastapi") is not None

    def test_rename_tag_missing_returns_none(
        self,
        tag_repo: TagRepository,
    ) -> None:
        """Renaming a missing tag should return None."""
        assert tag_repo.rename(99999, "python") is None

    def test_rename_tag_rejects_empty_name(
        self,
        tag_repo: TagRepository,
    ) -> None:
        """Renaming a tag to an empty name should fail."""
        tag = tag_repo.create("python")

        with pytest.raises(ValueError, match="cannot be empty"):
            tag_repo.rename(tag.pk, "   ")

    def test_rename_tag_rejects_duplicate_name(
        self,
        tag_repo: TagRepository,
    ) -> None:
        """Renaming a tag to an existing tag name should fail."""
        source = tag_repo.create("python")
        tag_repo.create("fastapi")

        with pytest.raises(ValueError, match='Tag "fastapi" already exists'):
            tag_repo.rename(source.pk, "fastapi")

    def test_rename_tag_translates_update_race(
        self,
        tag_repo: TagRepository,
        mocker: MockerFixture,
    ) -> None:
        """Update races should surface as duplicate-name ValueErrors."""
        tag = tag_repo.create("python")
        conflicting = tag_repo.create("fastapi")
        mocker.patch.object(
            tag_repo._db,
            "update",
            side_effect=RecordUpdateError("update failed"),
        )
        find_by_name = mocker.patch.object(
            tag_repo,
            "find_by_name",
            side_effect=[None, conflicting],
        )

        with pytest.raises(ValueError, match='Tag "fastapi" already exists'):
            tag_repo.rename(tag.pk, "fastapi")

        assert find_by_name.call_count == 2

    def test_rename_tag_preserves_non_duplicate_update_errors(
        self,
        tag_repo: TagRepository,
        mocker: MockerFixture,
    ) -> None:
        """Non-duplicate update failures should not be rewritten."""
        tag = tag_repo.create("python")
        mocker.patch.object(
            tag_repo._db,
            "update",
            side_effect=RecordUpdateError("disk full"),
        )

        with pytest.raises(RecordUpdateError, match="disk full"):
            tag_repo.rename(tag.pk, "fastapi")

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

    def test_list_in_use(
        self,
        tag_repo: TagRepository,
        idea_repo: IdeaRepository,
    ) -> None:
        """Only tags linked to ideas are returned."""
        _seed_tag_usage_data(tag_repo, idea_repo)

        tags = tag_repo.list_in_use()

        assert [tag.name for tag in tags] == ["python", "testing"]

    def test_list_in_use_returns_empty_when_no_links(
        self,
        tag_repo: TagRepository,
    ) -> None:
        """No linked tags should produce an empty list."""
        tag_repo.get_or_create("unused")

        assert tag_repo.list_in_use() == []

    def test_list_with_usage(
        self,
        tag_repo: TagRepository,
        idea_repo: IdeaRepository,
    ) -> None:
        """All tags are returned with idea usage counts."""
        _seed_tag_usage_data(tag_repo, idea_repo)

        tags_with_usage = tag_repo.list_with_usage()

        assert all(isinstance(tag, Tag) for tag, _usage in tags_with_usage)
        assert all(tag.pk > 0 for tag, _usage in tags_with_usage)
        assert [(tag.name, usage) for tag, usage in tags_with_usage] == [
            ("python", 2),
            ("testing", 1),
            ("unused", 0),
        ]

    def test_list_with_usage_raises_for_invalid_usage_projection(
        self,
        tag_repo: TagRepository,
        mocker: MockerFixture,
    ) -> None:
        """Unexpected non-int usage values should fail clearly."""
        mocker.patch.object(
            tag_repo._db,
            "select",
            return_value=_FakeTagUsageQuery(
                [
                    {
                        "pk": 1,
                        "name": "python",
                        "created_at": 1,
                        "updated_at": 1,
                        "usage": None,
                    }
                ]
            ),
        )

        with pytest.raises(TypeError, match="Expected int or str for usage"):
            tag_repo.list_with_usage()

    def test_list_with_usage_raises_for_non_numeric_usage_projection(
        self,
        tag_repo: TagRepository,
        mocker: MockerFixture,
    ) -> None:
        """Non-numeric string usage values should fail clearly."""
        mocker.patch.object(
            tag_repo._db,
            "select",
            return_value=_FakeTagUsageQuery(
                [
                    {
                        "pk": 1,
                        "name": "python",
                        "created_at": 1,
                        "updated_at": 1,
                        "usage": "abc",
                    }
                ]
            ),
        )

        with pytest.raises(
            TypeError,
            match="Expected int-compatible value for usage",
        ):
            tag_repo.list_with_usage()

    def test_list_with_usage_raises_for_invalid_name_projection(
        self,
        tag_repo: TagRepository,
        mocker: MockerFixture,
    ) -> None:
        """Unexpected non-string names should fail clearly."""
        mocker.patch.object(
            tag_repo._db,
            "select",
            return_value=_FakeTagUsageQuery(
                [
                    {
                        "pk": 1,
                        "name": None,
                        "created_at": 1,
                        "updated_at": 1,
                        "usage": 2,
                    }
                ]
            ),
        )

        with pytest.raises(TypeError, match="Expected str for name"):
            tag_repo.list_with_usage()

    def test_list_with_usage_raises_for_missing_usage_projection(
        self,
        tag_repo: TagRepository,
        mocker: MockerFixture,
    ) -> None:
        """Missing usage fields should fail clearly."""
        mocker.patch.object(
            tag_repo._db,
            "select",
            return_value=_FakeTagUsageQuery(
                [
                    {
                        "pk": 1,
                        "name": "python",
                        "created_at": 1,
                        "updated_at": 1,
                    }
                ]
            ),
        )

        with pytest.raises(KeyError, match="Missing projected field: usage"):
            tag_repo.list_with_usage()

    def test_list_with_usage_raises_for_missing_name_projection(
        self,
        tag_repo: TagRepository,
        mocker: MockerFixture,
    ) -> None:
        """Missing name fields should fail clearly."""
        mocker.patch.object(
            tag_repo._db,
            "select",
            return_value=_FakeTagUsageQuery(
                [
                    {
                        "pk": 1,
                        "created_at": 1,
                        "updated_at": 1,
                        "usage": 2,
                    }
                ]
            ),
        )

        with pytest.raises(KeyError, match="Missing projected field: name"):
            tag_repo.list_with_usage()

    def test_related_name_helper_raises_when_descriptor_name_missing(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Related-name helper should fail clearly when unavailable."""
        mocker.patch.object(
            tag_repo_module,
            "Idea",
            SimpleNamespace(tags=SimpleNamespace(related_name=None)),
        )

        with pytest.raises(
            RuntimeError,
            match=r"Idea\.tags related_name is unavailable",
        ):
            tag_repo_module._idea_tags_related_name()


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

    def test_rename_updates_only_title(
        self,
        idea_repo: IdeaRepository,
        group_repo: GroupRepository,
    ) -> None:
        """Rename should preserve body and group assignment."""
        source = group_repo.create("source")
        created = idea_repo.create(
            "Original",
            body="Body text",
            group_pk=source.pk,
        )

        renamed = idea_repo.rename(created.pk, "Renamed")

        assert renamed is not None
        assert renamed.title == "Renamed"
        assert renamed.body == "Body text"
        assert renamed.group.pk == source.pk

    def test_rename_missing_idea_returns_none(
        self,
        idea_repo: IdeaRepository,
    ) -> None:
        """Rename should return None for a missing idea."""
        assert idea_repo.rename(99999, "Renamed") is None

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

    def test_search_free_text_excludes_tag_only_matches(
        self,
        idea_repo: IdeaRepository,
        group_repo: GroupRepository,
    ) -> None:
        """Free-text should not return ideas matched only through tags."""
        source = group_repo.create("source")
        idea_repo.create(
            "No query text in title",
            body="No query text in body",
            tag_names=["needle"],
            group_pk=source.pk,
        )

        results = idea_repo.search("needle")

        assert results == []

    def test_search_free_text_excludes_group_only_matches(
        self,
        idea_repo: IdeaRepository,
        group_repo: GroupRepository,
    ) -> None:
        """Free-text should not return ideas matched only through groups."""
        source = group_repo.create("needle")
        idea_repo.create(
            "No query text in title",
            body="No query text in body",
            group_pk=source.pk,
        )

        results = idea_repo.search("needle")

        assert results == []

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

    def test_legacy_text_matches_cover_title_and_body_only(
        self,
        idea_repo: IdeaRepository,
    ) -> None:
        """Legacy fallback should only match visible title/body text."""
        title_match = idea_repo.create(
            "Title fallback marker",
            body="",
        )
        body_match = idea_repo.create(
            "No punctuation in title",
            body="Body-only fallback for body? queries",
        )

        title_results = idea_repo._legacy_text_matches("marker")
        body_results = idea_repo._legacy_text_matches("body?")

        assert title_match.pk in title_results
        assert body_results[body_match.pk][1] is not None
        assert idea_repo._legacy_text_matches("c++") == {}

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

    def test_search_text_matches_drop_fts_rows_without_visible_fragments(
        self,
        idea_repo: IdeaRepository,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """FTS rows with only hidden-field hits should still be ignored."""
        monkeypatch.setattr(
            idea_repo._search_backend,
            "search_text",
            lambda _text_query: [
                FtsSearchMatch(
                    idea_pk=42,
                    score=-1.0,
                    body_snippet="",
                    title_snippet="",
                    group_snippet="[[backend]]",
                    tag_snippet="[[python]]",
                )
            ],
        )

        assert idea_repo._search_text_matches("async python") == {}

    def test_search_results_structured_only_have_no_visible_matches(
        self,
        idea_repo: IdeaRepository,
        group_repo: GroupRepository,
    ) -> None:
        """Structured-only filters should return ideas without match rows."""
        backend = group_repo.create("backend")
        idea = idea_repo.create(
            "Grouped python",
            group_pk=backend.pk,
            tag_names=["python"],
        )

        structured_only = idea_repo.search_results(
            parse_search_query("tag:python group:backend")
        )
        assert len(structured_only) == 1
        assert structured_only[0].idea.pk == idea.pk
        assert structured_only[0].matches == ()

    def test_search_results_text_plus_filter_add_title_fragment(
        self,
        idea_repo: IdeaRepository,
    ) -> None:
        """Text plus structured filters should keep visible text fragments."""
        idea = idea_repo.create("Grouped python", tag_names=["python"])

        results = idea_repo.search_results(
            parse_search_query("python tag:python")
        )

        assert len(results) == 1
        assert results[0].idea.pk == idea.pk
        assert results[0].matches == (
            SearchMatchFragment(
                source="title",
                text="Grouped [[python]]",
                rank=0,
                is_synthetic=True,
            ),
        )

    def test_search_result_fragment_helpers_cover_fallback_paths(
        self,
        idea_repo: IdeaRepository,
    ) -> None:
        """Fragment helpers should cover no-op and dedupe branches."""
        assert (
            idea_repo._mark_legacy_match("plain text", "missing")
            == "plain text"
        )
        duplicate = SearchMatchFragment(
            source="title",
            text="Title: [[python]]",
            rank=0,
            is_synthetic=True,
        )
        assert idea_repo._merge_fragments(
            (duplicate,),
            (duplicate,),
        ) == (duplicate,)
        assert idea_repo._mark_exact_text("python") == "[[python]]"
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

    def test_list_positions_and_delete_for_idea(
        self,
        idea_cursor_state_repo: IdeaCursorStateRepository,
        idea_repo: IdeaRepository,
    ) -> None:
        """Cursor positions should list and delete persisted state."""
        idea = idea_repo.create("Cursor")
        idea_cursor_state_repo.set_position(idea.pk, 9)

        assert idea_cursor_state_repo.list_positions() == {idea.pk: 9}

        idea_cursor_state_repo.delete_for_idea(idea.pk)
        assert idea_cursor_state_repo.list_positions() == {}

    def test_list_positions_raises_for_non_int_idea_id(
        self,
        idea_cursor_state_repo: IdeaCursorStateRepository,
        mocker: MockerFixture,
    ) -> None:
        """Unexpected non-int idea IDs should fail clearly."""

        class _FakeCursorStateQuery:
            def order(
                self,
                field: str,
            ) -> _FakeCursorStateQuery:
                assert field == "updated_at"
                return self

            @staticmethod
            def fetch_all() -> list[SimpleNamespace]:
                return [
                    SimpleNamespace(
                        idea_id="oops",
                        body_cursor_position=1,
                    )
                ]

        mocker.patch.object(
            idea_cursor_state_repo._db,
            "select",
            return_value=_FakeCursorStateQuery(),
        )

        with pytest.raises(
            TypeError,
            match=r"Expected IdeaCursorState\.idea_id",
        ):
            idea_cursor_state_repo.list_positions()


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

    def test_rename_group(self, group_repo: GroupRepository) -> None:
        """Group rename updates the stored name."""
        group = group_repo.create("backend")

        renamed = group_repo.rename(group.pk, "FrontEnd")

        assert renamed is not None
        assert renamed.name == "frontend"
        assert group_repo.find_by_name("frontend") is not None

    def test_rename_group_rejects_duplicate(
        self,
        group_repo: GroupRepository,
    ) -> None:
        """Renaming to an existing group name should fail."""
        source = group_repo.create("source")
        group_repo.create("target")

        with pytest.raises(ValueError, match="already exists"):
            group_repo.rename(source.pk, "target")

    def test_rename_group_rejects_empty_name(
        self,
        group_repo: GroupRepository,
    ) -> None:
        """Renaming to an empty name should fail."""
        group = group_repo.create("backend")

        with pytest.raises(ValueError, match="cannot be empty"):
            group_repo.rename(group.pk, "   ")

    def test_rename_group_missing_returns_none(
        self,
        group_repo: GroupRepository,
    ) -> None:
        """Renaming a missing group should return None."""
        assert group_repo.rename(99999, "backend") is None

    def test_rename_group_translates_update_race(
        self,
        group_repo: GroupRepository,
        mocker: MockerFixture,
    ) -> None:
        """Update races should surface as duplicate-name ValueErrors."""
        group = group_repo.create("backend")
        conflicting = group_repo.create("frontend")
        mocker.patch.object(
            group_repo._db,
            "update",
            side_effect=RecordUpdateError("update failed"),
        )
        find_by_name = mocker.patch.object(
            group_repo,
            "find_by_name",
            side_effect=[None, conflicting],
        )

        with pytest.raises(ValueError, match='Group "frontend" already exists'):
            group_repo.rename(group.pk, "frontend")

        assert find_by_name.call_count == 2

    def test_rename_group_preserves_non_duplicate_update_errors(
        self,
        group_repo: GroupRepository,
        mocker: MockerFixture,
    ) -> None:
        """Non-duplicate update failures should not be rewritten."""
        group = group_repo.create("backend")
        mocker.patch.object(
            group_repo._db,
            "update",
            side_effect=RecordUpdateError("disk full"),
        )

        with pytest.raises(RecordUpdateError, match="disk full"):
            group_repo.rename(group.pk, "frontend")

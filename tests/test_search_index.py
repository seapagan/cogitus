"""Tests for FTS-backed search index synchronization."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.search import parse_search_query
from cogitus.search.backend import _build_fts_query, _choose_snippet

if TYPE_CHECKING:
    import pytest
    from sqliter import SqliterDB

    from cogitus.repositories.idea_repo import IdeaRepository
    from cogitus.services.idea_service import IdeaService


def test_search_index_syncs_create_update_and_delete(
    service: IdeaService,
) -> None:
    """Indexed search should follow idea lifecycle operations."""
    idea = service.create_idea(
        "Original title",
        body="Original body text",
        tags=["python"],
    )

    assert [item.title for item in service.search_ideas("original")] == [
        "Original title",
    ]

    service.update_idea(
        idea.pk,
        "Updated title",
        "Updated body text",
        tags=["rust"],
    )

    assert service.search_ideas("original") == []
    assert [item.title for item in service.search_ideas("updated")] == [
        "Updated title",
    ]

    service.delete_idea(idea.pk)

    assert service.search_ideas("updated") == []


def test_search_index_rebuild_restores_removed_documents(
    db: SqliterDB,
    idea_repo: IdeaRepository,
    service: IdeaService,
) -> None:
    """Rebuilding the index should restore missing FTS rows."""
    idea = service.create_idea(
        "Rebuild target",
        body="Searchable body text",
        tags=["python"],
    )

    db.connect().execute(
        "DELETE FROM idea_search WHERE rowid = ?;",
        (idea.pk,),
    )
    db.connect().commit()

    assert service.search_ideas("rebuild") == []

    idea_repo.rebuild_search_index()

    assert [item.title for item in service.search_ideas("rebuild")] == [
        "Rebuild target",
    ]


def test_search_index_refreshes_after_group_move(
    service: IdeaService,
) -> None:
    """Group-derived indexed text should update after bulk reassignment."""
    source = service.create_group("source")
    target = service.create_group("target")
    service.create_idea("Grouped idea", group_pk=source.pk)

    assert [item.title for item in service.search_ideas("source")] == [
        "Grouped idea",
    ]

    service.delete_group(source.pk, move_to_group_pk=target.pk)

    assert service.search_ideas("source") == []
    assert [item.title for item in service.search_ideas("target")] == [
        "Grouped idea",
    ]


def test_search_large_dataset_stays_deduplicated(
    service: IdeaService,
) -> None:
    """Moderately larger datasets should still return unique matches."""
    for index in range(40):
        tags = ["python"] if index % 3 == 0 else ["notes"]
        body = "python body reference" if index % 5 == 0 else "plain text"
        service.create_idea(f"Idea {index}", body=body, tags=tags)

    results = service.search_ideas("python")
    result_pks = [idea.pk for idea in results]

    assert len(results) >= 8
    assert len(result_pks) == len(set(result_pks))


def test_build_fts_query_rejects_safe_but_tokenless_input() -> None:
    """Hyphen-only text should not produce an FTS query."""
    assert _build_fts_query("---") is None


def test_build_fts_query_tokenizes_punctuation_queries() -> None:
    """Common punctuation should not block token extraction for FTS."""
    expected = '"node"* AND "js"* AND "c"*'
    assert _build_fts_query("node.js? c++") == expected


def test_punctuation_queries_stay_on_fts_path(
    service: IdeaService,
    idea_repo: IdeaRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Punctuation-bearing text queries should not use legacy fallback."""
    service.create_idea(
        "Node.js runtime notes",
        body="Working notes about node.js internals",
    )

    def fail_legacy_fallback(
        _text_query: str,
    ) -> dict[int, tuple[float, str | None]]:
        msg = "punctuation query should stay on the FTS path"
        raise AssertionError(msg)

    monkeypatch.setattr(
        idea_repo,
        "_legacy_text_matches",
        fail_legacy_fallback,
    )

    results = idea_repo.search_results(parse_search_query("node.js"))

    assert [result.idea.title for result in results] == [
        "Node.js runtime notes"
    ]


def test_choose_snippet_returns_none_when_no_candidate_has_text() -> None:
    """Blank snippet candidates should collapse to None."""
    assert _choose_snippet(body_snippet=" ", title_snippet="\n\t") is None


def test_choose_snippet_prefers_body_then_title_then_plain_fallback() -> None:
    """Snippet chooser should exercise all highlight/fallback branches."""
    assert (
        _choose_snippet(
            body_snippet="Body [[match]] text",
            title_snippet="Title [[match]] text",
        )
        == "Body match text"
    )
    assert (
        _choose_snippet(
            body_snippet="body without highlight",
            title_snippet="Title [[match]] text",
        )
        == "Title match text"
    )
    assert (
        _choose_snippet(
            body_snippet="body without highlight",
            title_snippet="plain title",
        )
        == "body without highlight"
    )
    assert (
        _choose_snippet(
            body_snippet=" ",
            title_snippet=" plain   title ",
        )
        == "plain title"
    )

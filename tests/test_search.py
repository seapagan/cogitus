"""Tests for search functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogitus.models.idea import Idea

if TYPE_CHECKING:
    from sqliter import SqliterDB

    from cogitus.services.idea_service import IdeaService


class TestSearch:
    """Tests for idea search across visible text and structured filters."""

    def test_search_by_title(
        self,
        service: IdeaService,
        sample_ideas: list[Idea],
    ) -> None:
        """Ideas matching title are found."""
        results = service.search_ideas("metaclasses")
        assert len(results) == 1
        assert results[0].title == "Python metaclasses"

    def test_search_by_body(
        self,
        service: IdeaService,
        sample_ideas: list[Idea],
    ) -> None:
        """Ideas matching body text are found."""
        results = service.search_ideas("pitfalls")
        assert len(results) == 1
        assert results[0].title == "Async patterns"

    def test_search_does_not_match_tag_name_without_filter(
        self,
        service: IdeaService,
        sample_ideas: list[Idea],
    ) -> None:
        """Tag names should not qualify plain free-text results."""
        results = service.search_ideas("architecture")
        assert results == []

    def test_search_across_fields(
        self,
        service: IdeaService,
        sample_ideas: list[Idea],
    ) -> None:
        """Ideas matching in any field are found."""
        results = service.search_ideas("python")
        assert len(results) == 2

    def test_search_case_insensitive(
        self,
        service: IdeaService,
        sample_ideas: list[Idea],
    ) -> None:
        """Search is case-insensitive."""
        results = service.search_ideas("REST")
        assert len(results) == 1
        assert results[0].title == "REST API design"

    def test_search_no_duplicates(
        self,
        service: IdeaService,
        sample_ideas: list[Idea],
    ) -> None:
        """Search results are deduplicated."""
        results = service.search_ideas("python")
        pks = [r.pk for r in results]
        assert len(pks) == len(set(pks))

    def test_search_empty_query(
        self,
        service: IdeaService,
        sample_ideas: list[Idea],
    ) -> None:
        """Empty search returns all ideas."""
        results = service.search_ideas("")
        assert len(results) == 3

    def test_search_no_results(
        self,
        service: IdeaService,
        sample_ideas: list[Idea],
    ) -> None:
        """Search with no matches returns empty list."""
        results = service.search_ideas("nonexistent_xyz")
        assert len(results) == 0

    def test_search_ranks_stronger_title_match_before_body_match(
        self,
        service: IdeaService,
    ) -> None:
        """Title/body strength should outrank weaker body-only matches."""
        service.create_idea(
            "Python architecture",
            "Strong title and body match",
        )
        service.create_idea(
            "Secondary note",
            "Python architecture references in body only",
        )

        results = service.search_ideas("python architecture")

        assert [idea.title for idea in results] == [
            "Python architecture",
            "Secondary note",
        ]

    def test_search_breaks_equal_scores_by_recency(
        self,
        db: SqliterDB,
        service: IdeaService,
    ) -> None:
        """Equal-score text matches should fall back to recency order."""
        older = service.create_idea("Python title", "Same match strength")
        newer = service.create_idea("Python title", "Same match strength")
        db.update_where(
            Idea,
            where={"pk": older.pk},
            values={"updated_at": 1},
        )
        db.update_where(
            Idea,
            where={"pk": newer.pk},
            values={"updated_at": 10},
        )

        results = service.search_ideas("python")

        assert [idea.pk for idea in results[:2]] == [newer.pk, older.pk]

    def test_search_by_group_filter(
        self,
        service: IdeaService,
    ) -> None:
        """group: filter should match ideas by exact group name."""
        backend = service.create_group("backend")
        service.create_idea("Backend only", group_pk=backend.pk)
        service.create_idea("Default only")

        results = service.search_ideas("group:backend")

        assert len(results) == 1
        assert results[0].title == "Backend only"

    def test_search_by_tag_filter(
        self,
        service: IdeaService,
        sample_ideas: list[Idea],
    ) -> None:
        """tag: filter should still match ideas by exact tag name."""
        results = service.search_ideas("tag:architecture")
        assert len(results) == 1
        assert results[0].title == "REST API design"

    def test_search_tag_filters_default_to_and(
        self,
        service: IdeaService,
    ) -> None:
        """Multiple tag filters without connector should default to AND."""
        service.create_idea("A", tags=["python"])
        service.create_idea("B", tags=["api"])
        service.create_idea("C", tags=["python", "api"])

        results = service.search_ideas("tag:python tag:api")

        assert [idea.title for idea in results] == ["C"]

    def test_search_tag_filters_support_explicit_or(
        self,
        service: IdeaService,
    ) -> None:
        """Explicit OR should broaden structured tag filters."""
        service.create_idea("A", tags=["python"])
        service.create_idea("B", tags=["api"])
        service.create_idea("C", tags=["python", "api"])

        results = service.search_ideas("tag:python or tag:api")
        titles = {idea.title for idea in results}

        assert titles == {"A", "B", "C"}

    def test_search_mixed_text_and_structured_filter(
        self,
        service: IdeaService,
    ) -> None:
        """Text terms should be intersected with structured filters."""
        service.create_idea("Python backend", tags=["api"])
        service.create_idea("Python frontend", tags=["ui"])
        service.create_idea("Rust backend", tags=["api"])

        results = service.search_ideas("python tag:api")

        assert len(results) == 1
        assert results[0].title == "Python backend"

    def test_search_invalid_operator_token_treated_as_text(
        self,
        service: IdeaService,
    ) -> None:
        """Invalid operator fragments should degrade to plain text search."""
        service.create_idea("tag: playground")
        service.create_idea("ordinary")

        results = service.search_ideas("tag:")

        assert len(results) == 1
        assert results[0].title == "tag: playground"

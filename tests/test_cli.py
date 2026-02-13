"""Tests for CLI commands."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from cogitus.cli.commands import app
from cogitus.cli.formatters import (
    format_idea_markdown,
    format_ideas_json,
    format_ideas_markdown,
    format_ideas_simple,
    format_ideas_table,
)

if TYPE_CHECKING:
    from sqliter import SqliterDB

    from cogitus.models.idea import Idea
    from cogitus.services.idea_service import IdeaService

runner = CliRunner()


@pytest.fixture
def cli_db(db: SqliterDB) -> SqliterDB:
    """Alias the shared db fixture for CLI tests."""
    return db


@pytest.fixture
def cli_service(service: IdeaService) -> IdeaService:
    """Alias the shared service fixture for CLI tests."""
    return service


@pytest.fixture
def cli_ideas(cli_service: IdeaService) -> list[Idea]:
    """Create sample ideas for CLI tests."""
    return [
        cli_service.create_idea(
            "First idea",
            "Body of first idea",
            ["python", "testing"],
        ),
        cli_service.create_idea(
            "Second idea",
            "Body of second idea",
            ["rust"],
        ),
        cli_service.create_idea(
            "Third idea",
            "Body of third idea",
            [],
        ),
    ]


class TestListCommand:
    """Tests for the list command."""

    def test_list_empty(self, cli_db: SqliterDB) -> None:
        """List with empty database shows no ideas message."""
        with patch("cogitus.cli.commands.get_db", return_value=cli_db):
            result = runner.invoke(app, ["list"])
            assert result.exit_code == 0
            assert "No ideas found" in result.output

    def test_list_simple(
        self,
        cli_db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """List shows ideas in simple format by default."""
        with patch("cogitus.cli.commands.get_db", return_value=cli_db):
            result = runner.invoke(app, ["list"])
            assert result.exit_code == 0
            assert "First idea" in result.output
            assert "Second idea" in result.output
            assert "[python]" in result.output

    def test_list_json(self, cli_db: SqliterDB, cli_ideas: list[Idea]) -> None:
        """List with json format outputs JSON."""
        with patch("cogitus.cli.commands.get_db", return_value=cli_db):
            result = runner.invoke(app, ["list", "--format", "json"])
            assert result.exit_code == 0
            assert '"title": "First idea"' in result.output
            assert '"python"' in result.output

    def test_list_table(self, cli_db: SqliterDB, cli_ideas: list[Idea]) -> None:
        """List with table format outputs ASCII table."""
        with patch("cogitus.cli.commands.get_db", return_value=cli_db):
            result = runner.invoke(app, ["list", "--format", "table"])
            assert result.exit_code == 0
            assert "Title" in result.output
            assert "First idea" in result.output

    def test_list_with_query(
        self,
        cli_db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """List with query filters results."""
        with patch("cogitus.cli.commands.get_db", return_value=cli_db):
            result = runner.invoke(app, ["list", "--query", "rust"])
            assert result.exit_code == 0
            assert "Second idea" in result.output
            assert "First idea" not in result.output

    def test_list_with_limit(
        self,
        cli_db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """List with limit restricts results."""
        with patch("cogitus.cli.commands.get_db", return_value=cli_db):
            result = runner.invoke(app, ["list", "--limit", "1"])
            assert result.exit_code == 0
            # Only one idea line should appear (format: "[pk] Title ...")
            lines = [line for line in result.output.strip().split("\n") if line]
            assert len(lines) == 1


class TestExportCommand:
    """Tests for the export command."""

    def test_export_all_json(
        self,
        cli_db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """Export without PK outputs all ideas as JSON."""
        with patch("cogitus.cli.commands.get_db", return_value=cli_db):
            result = runner.invoke(app, ["export"])
            assert result.exit_code == 0
            assert '"title": "First idea"' in result.output
            assert '"title": "Second idea"' in result.output

    def test_export_single_json(
        self,
        cli_db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """Export with PK outputs single idea as JSON."""
        with patch("cogitus.cli.commands.get_db", return_value=cli_db):
            result = runner.invoke(app, ["export", str(cli_ideas[0].pk)])
            assert result.exit_code == 0
            assert '"title": "First idea"' in result.output
            assert "Second idea" not in result.output

    def test_export_single_markdown(
        self,
        cli_db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """Export with PK and markdown format."""
        with patch("cogitus.cli.commands.get_db", return_value=cli_db):
            result = runner.invoke(
                app,
                ["export", str(cli_ideas[0].pk), "--format", "markdown"],
            )
            assert result.exit_code == 0
            assert "# [" in result.output
            assert "First idea" in result.output

    def test_export_all_markdown(
        self,
        cli_db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """Export all ideas as markdown document."""
        with patch("cogitus.cli.commands.get_db", return_value=cli_db):
            result = runner.invoke(app, ["export", "--format", "markdown"])
            assert result.exit_code == 0
            assert "First idea" in result.output
            assert "---" in result.output

    def test_export_not_found(self, cli_db: SqliterDB) -> None:
        """Export with non-existent PK shows error."""
        with patch("cogitus.cli.commands.get_db", return_value=cli_db):
            result = runner.invoke(app, ["export", "999"])
            assert result.exit_code == 1
            assert "not found" in result.output


class TestDeleteCommand:
    """Tests for the delete command."""

    def test_delete_force(
        self,
        cli_db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """Delete with force skips confirmation."""
        pk = cli_ideas[0].pk
        with (
            patch("cogitus.cli.commands.get_db", return_value=cli_db),
            patch.object(cli_db, "close"),
        ):
            result = runner.invoke(app, ["delete", str(pk), "--force"])
            assert result.exit_code == 0
            assert "Deleted" in result.output

            # Verify deletion by checking pk not in results
            verify_result = runner.invoke(app, ["list", "--format", "json"])
            remaining = json.loads(verify_result.output)
            assert pk not in [idea["pk"] for idea in remaining]

    def test_delete_confirm_yes(
        self,
        cli_db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """Delete with confirmation accepts yes."""
        pk = cli_ideas[0].pk
        with (
            patch("cogitus.cli.commands.get_db", return_value=cli_db),
            patch.object(cli_db, "close"),
        ):
            result = runner.invoke(app, ["delete", str(pk)], input="y")
            assert result.exit_code == 0
            assert "Deleted" in result.output

            # Verify deletion by checking pk not in results
            verify_result = runner.invoke(app, ["list", "--format", "json"])
            remaining = json.loads(verify_result.output)
            assert pk not in [idea["pk"] for idea in remaining]

    def test_delete_confirm_no(
        self,
        cli_db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """Delete with confirmation respects no."""
        pk = cli_ideas[0].pk
        with patch("cogitus.cli.commands.get_db", return_value=cli_db):
            result = runner.invoke(app, ["delete", str(pk)], input="n")
            assert result.exit_code == 0
            assert "Aborted" in result.output
            assert "Deleted" not in result.output

    def test_delete_not_found(self, cli_db: SqliterDB) -> None:
        """Delete with non-existent PK shows error."""
        with patch("cogitus.cli.commands.get_db", return_value=cli_db):
            result = runner.invoke(app, ["delete", "999", "--force"])
            assert result.exit_code == 1
            assert "not found" in result.output


class TestFormatters:
    """Tests for formatter functions."""

    def test_format_ideas_simple_empty(self) -> None:
        """Simple formatter handles empty list."""
        result = format_ideas_simple([])
        assert result == "No ideas found."

    def test_format_ideas_table_empty(self) -> None:
        """Table formatter handles empty list."""
        result = format_ideas_table([])
        assert result == "No ideas found."

    def test_format_ideas_markdown_empty(self) -> None:
        """Markdown formatter handles empty list."""
        result = format_ideas_markdown([])
        assert result == "No ideas found."

    def test_format_ideas_json_empty(self) -> None:
        """JSON formatter handles empty list."""
        result = format_ideas_json([])
        assert result == "[]"

    def test_format_idea_markdown(
        self,
        cli_service: IdeaService,
    ) -> None:
        """Markdown formatter produces correct structure."""
        idea = cli_service.create_idea(
            "Test idea",
            "Test body content",
            ["tag1", "tag2"],
        )
        result = format_idea_markdown(idea)
        assert "# [" in result
        assert "Test idea" in result
        assert "Test body content" in result
        assert "`tag1`" in result
        assert "`tag2`" in result

    def test_format_idea_markdown_no_tags(
        self,
        cli_service: IdeaService,
    ) -> None:
        """Markdown formatter handles ideas without tags."""
        idea = cli_service.create_idea("No tags", "Body")
        result = format_idea_markdown(idea)
        assert "# [" in result
        assert "No tags" in result
        assert "Tags:" not in result

    def test_format_ideas_json_structure(
        self,
        cli_service: IdeaService,
    ) -> None:
        """JSON formatter produces correct structure."""
        idea = cli_service.create_idea("Test", "Body", ["py"])
        result = format_ideas_json([idea])
        assert '"pk"' in result
        assert '"title"' in result
        assert '"body"' in result
        assert '"tags"' in result
        assert '"group"' in result
        assert '"created_at"' in result
        assert '"updated_at"' in result

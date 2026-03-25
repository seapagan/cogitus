"""Tests for CLI commands."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
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
from cogitus.metadata import AppMetadata

if TYPE_CHECKING:
    from pytest_mock import MockerFixture
    from sqliter import SqliterDB

    from cogitus.models.idea import Idea
    from cogitus.services.idea_service import IdeaService

runner = CliRunner()


@pytest.fixture
def cli_ideas(service: IdeaService) -> list[Idea]:
    """Create sample ideas for CLI tests."""
    return [
        service.create_idea(
            "First idea",
            "Body of first idea",
            ["python", "testing"],
        ),
        service.create_idea(
            "Second idea",
            "Body of second idea",
            ["rust"],
        ),
        service.create_idea(
            "Third idea",
            "Body of third idea",
            [],
        ),
    ]


class TestListCommand:
    """Tests for the list command."""

    def test_list_empty(self, db: SqliterDB) -> None:
        """List with empty database shows no ideas message."""
        with patch("cogitus.cli.commands.get_db", return_value=db):
            result = runner.invoke(app, ["list"])
            assert result.exit_code == 0
            assert "No ideas found" in result.output

    def test_list_simple(
        self,
        db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """List shows ideas in simple format by default."""
        with patch("cogitus.cli.commands.get_db", return_value=db):
            result = runner.invoke(app, ["list"])
            assert result.exit_code == 0
            assert "First idea" in result.output
            assert "Second idea" in result.output
            assert "[python]" in result.output

    def test_list_json(self, db: SqliterDB, cli_ideas: list[Idea]) -> None:
        """List with json format outputs JSON."""
        with patch("cogitus.cli.commands.get_db", return_value=db):
            result = runner.invoke(app, ["list", "--format", "json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            titles = {item["title"] for item in data}
            assert "First idea" in titles
            all_tags = {tag for item in data for tag in item["tags"]}
            assert "python" in all_tags

    def test_list_table(self, db: SqliterDB, cli_ideas: list[Idea]) -> None:
        """List with table format outputs ASCII table."""
        with patch("cogitus.cli.commands.get_db", return_value=db):
            result = runner.invoke(app, ["list", "--format", "table"])
            assert result.exit_code == 0
            assert "Title" in result.output
            assert "First idea" in result.output

    def test_list_with_query(
        self,
        db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """List with plain-text query filters visible text results."""
        with patch("cogitus.cli.commands.get_db", return_value=db):
            result = runner.invoke(app, ["list", "--query", "second"])
            assert result.exit_code == 0
            assert "Second idea" in result.output
            assert "First idea" not in result.output

    def test_list_with_tag_operator_query(
        self,
        db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """List query should support structured tag operators."""
        with patch("cogitus.cli.commands.get_db", return_value=db):
            result = runner.invoke(app, ["list", "--query", "tag:python"])
            assert result.exit_code == 0
            assert "First idea" in result.output
            assert "Second idea" not in result.output

    def test_list_with_group_and_tag_query(
        self,
        db: SqliterDB,
        service: IdeaService,
    ) -> None:
        """List query should support combined group and tag operators."""
        backend = service.create_group("backend")
        service.create_idea(
            "Backend python",
            tags=["python"],
            group_pk=backend.pk,
        )
        service.create_idea("Backend rust", tags=["rust"], group_pk=backend.pk)
        service.create_idea("Default python", tags=["python"])

        with patch("cogitus.cli.commands.get_db", return_value=db):
            result = runner.invoke(
                app,
                ["list", "--query", "group:backend and tag:python"],
            )
            assert result.exit_code == 0
            assert "Backend python" in result.output
            assert "Backend rust" not in result.output
            assert "Default python" not in result.output

    def test_list_with_limit(
        self,
        db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """List with limit restricts results."""
        with patch("cogitus.cli.commands.get_db", return_value=db):
            result = runner.invoke(app, ["list", "--limit", "1"])
            assert result.exit_code == 0
            # Only one idea line should appear (format: "[pk] Title ...")
            idea_lines = [
                line
                for line in result.output.strip().split("\n")
                if re.match(r"^\[\d+\]\s", line)
            ]
            assert len(idea_lines) == 1


class TestExportCommand:
    """Tests for the export command."""

    def test_export_all_json(
        self,
        db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """Export without PK outputs all ideas as JSON."""
        with patch("cogitus.cli.commands.get_db", return_value=db):
            result = runner.invoke(app, ["export"])
            assert result.exit_code == 0
            assert '"title": "First idea"' in result.output
            assert '"title": "Second idea"' in result.output

    def test_export_single_json(
        self,
        db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """Export with PK outputs single idea as JSON."""
        with patch("cogitus.cli.commands.get_db", return_value=db):
            result = runner.invoke(app, ["export", str(cli_ideas[0].pk)])
            assert result.exit_code == 0
            assert '"title": "First idea"' in result.output
            assert "Second idea" not in result.output

    def test_export_single_markdown(
        self,
        db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """Export with PK and markdown format."""
        with patch("cogitus.cli.commands.get_db", return_value=db):
            result = runner.invoke(
                app,
                ["export", str(cli_ideas[0].pk), "--format", "markdown"],
            )
            assert result.exit_code == 0
            assert "# [" in result.output
            assert "First idea" in result.output

    def test_export_all_markdown(
        self,
        db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """Export all ideas as markdown document."""
        with patch("cogitus.cli.commands.get_db", return_value=db):
            result = runner.invoke(app, ["export", "--format", "markdown"])
            assert result.exit_code == 0
            assert "First idea" in result.output
            assert "---" in result.output

    def test_export_not_found(self, db: SqliterDB) -> None:
        """Export with non-existent PK shows error."""
        with patch("cogitus.cli.commands.get_db", return_value=db):
            result = runner.invoke(app, ["export", "999"])
            assert result.exit_code == 1
            assert "not found" in result.output


class TestDeleteCommand:
    """Tests for the delete command."""

    def test_delete_force(
        self,
        db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """Delete with force skips confirmation."""
        pk = cli_ideas[0].pk
        with (
            patch("cogitus.cli.commands.get_db", return_value=db),
            patch.object(db, "close"),
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
        db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """Delete with confirmation accepts yes."""
        pk = cli_ideas[0].pk
        with (
            patch("cogitus.cli.commands.get_db", return_value=db),
            patch.object(db, "close"),
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
        db: SqliterDB,
        cli_ideas: list[Idea],
    ) -> None:
        """Delete with confirmation respects no."""
        pk = cli_ideas[0].pk
        with patch("cogitus.cli.commands.get_db", return_value=db):
            result = runner.invoke(app, ["delete", str(pk)], input="n")
            assert result.exit_code == 0
            assert "Aborted" in result.output
            assert "Deleted" not in result.output

    def test_delete_not_found(self, db: SqliterDB) -> None:
        """Delete with non-existent PK shows error."""
        with patch("cogitus.cli.commands.get_db", return_value=db):
            result = runner.invoke(app, ["delete", "999", "--force"])
            assert result.exit_code == 1
            assert "not found" in result.output


class TestVersionOption:
    """Tests for the global version option."""

    def test_version_outputs_metadata(self, mocker: MockerFixture) -> None:
        """The version option should print metadata and exit cleanly."""
        mocker.patch(
            "cogitus.cli.commands.get_app_metadata",
            return_value=AppMetadata(
                title="Cogitus",
                version="1.2.3",
                summary="Test summary",
            ),
        )
        get_db = mocker.patch("cogitus.cli.commands.get_db")

        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert result.output == (
            "Test summary\n"
            "© "
            f"{datetime.now(tz=timezone.utc).year} "
            "Grant Ramsay (seapagan)\n"
            "Version: 1.2.3\n"
        )
        get_db.assert_not_called()


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
        service: IdeaService,
    ) -> None:
        """Markdown formatter produces correct structure."""
        idea = service.create_idea(
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
        service: IdeaService,
    ) -> None:
        """Markdown formatter handles ideas without tags."""
        idea = service.create_idea("No tags", "Body")
        result = format_idea_markdown(idea)
        assert "# [" in result
        assert "No tags" in result
        assert "Tags:" not in result

    def test_format_ideas_json_structure(
        self,
        service: IdeaService,
    ) -> None:
        """JSON formatter produces correct structure."""
        idea = service.create_idea("Test", "Body", ["py"])
        result = format_ideas_json([idea])
        data = json.loads(result)
        assert len(data) == 1
        expected_keys = {
            "pk",
            "title",
            "body",
            "tags",
            "group",
            "created_at",
            "updated_at",
        }
        assert expected_keys <= data[0].keys()

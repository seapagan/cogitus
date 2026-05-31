"""Tests for CLI commands."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from typer.testing import CliRunner

from cogitus.api.managers.auth_manager import MCPAuthManager
from cogitus.cli.commands import (
    COGITUS_API_DB_PATH_ENV,
    COGITUS_MCP_DB_PATH_ENV,
    app,
)
from cogitus.cli.formatters import (
    format_idea_markdown,
    format_ideas_json,
    format_ideas_markdown,
    format_ideas_simple,
    format_ideas_table,
)
from cogitus.config import AppSettings, get_mcp_auth_settings, get_settings
from cogitus.metadata import AppMetadata

if TYPE_CHECKING:
    from pathlib import Path

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
        """List query should support subtree group and tag operators."""
        backend = service.create_group("backend")
        api = service.create_group("api", parent_pk=backend.pk)
        service.create_idea(
            "Backend python",
            tags=["python"],
            group_pk=backend.pk,
        )
        service.create_idea(
            "API python",
            tags=["python"],
            group_pk=api.pk,
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
            assert "API python" in result.output
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


class TestApiServeCommand:
    """Tests for the API serve command."""

    def test_api_serve_uses_uvicorn_factory(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Serve command should invoke uvicorn with the app factory."""
        monkeypatch.delenv(COGITUS_API_DB_PATH_ENV, raising=False)
        db_path = tmp_path / "cogitus-api.db"

        try:
            with patch("uvicorn.run") as mock_run:
                result = runner.invoke(
                    app,
                    [
                        "api",
                        "serve",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "9001",
                        "--reload",
                        "--db-path",
                        str(db_path),
                    ],
                )

            assert result.exit_code == 0
            assert os.environ[COGITUS_API_DB_PATH_ENV] == str(db_path)
            mock_run.assert_called_once_with(
                "cogitus.api.main:create_api_app",
                host="127.0.0.1",
                port=9001,
                reload=True,
                factory=True,
            )
        finally:
            monkeypatch.delenv(COGITUS_API_DB_PATH_ENV, raising=False)

    def test_api_serve_clears_db_path_env_when_not_provided(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Serve command should clear any prior API DB path override."""
        monkeypatch.setenv(COGITUS_API_DB_PATH_ENV, "stale-value")

        with patch("uvicorn.run") as mock_run:
            result = runner.invoke(app, ["api", "serve"])

        assert result.exit_code == 0
        assert COGITUS_API_DB_PATH_ENV not in os.environ
        mock_run.assert_called_once_with(
            "cogitus.api.main:create_api_app",
            host="127.0.0.1",
            port=8000,
            reload=False,
            factory=True,
        )

    def test_api_serve_requires_api_extra(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Serve command should fail cleanly without the optional API deps."""

        def fake_import_module(name: str) -> object:
            if name == "uvicorn":
                raise ModuleNotFoundError
            return __import__(name)

        monkeypatch.setattr(
            "cogitus.cli.commands.importlib.import_module",
            fake_import_module,
        )

        result = runner.invoke(app, ["api", "serve"])

        assert result.exit_code == 1
        assert "pip install cogitus[api]" in result.output


class TestApiAuthCommand:
    """Tests for API auth bootstrap commands."""

    def test_api_set_auth_persists_credentials(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """set-auth should persist a hashed password and generated secret."""
        monkeypatch.setattr(
            "simple_toml_settings.settings.xdg_config_home",
            lambda: tmp_path,
        )
        AppSettings._instances.clear()
        monkeypatch.setattr(
            "cogitus.cli.commands._import_optional_module",
            lambda _: SimpleNamespace(
                hash_password=lambda password: f"hashed::{password}"
            ),
        )
        monkeypatch.setattr(
            "cogitus.cli.commands.token_urlsafe",
            lambda _: "generated-secret",
        )

        result = runner.invoke(
            app,
            [
                "api",
                "set-auth",
                "--username",
                "  api-user  ",
                "--password",
                "secret-password",
            ],
        )

        AppSettings._instances.clear()
        settings = get_settings()
        expected_digest = "hashed::secret-password"
        generated_key = "generated-secret"

        assert result.exit_code == 0
        assert "Configured API auth for user 'api-user'." in result.output
        assert settings.api_auth_username == "api-user"
        assert settings.api_auth_password_hash == expected_digest
        assert settings.api_auth_jwt_secret == generated_key

    def test_api_set_auth_rotates_existing_secret(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """set-auth should rotate the JWT secret when requested."""
        monkeypatch.setattr(
            "simple_toml_settings.settings.xdg_config_home",
            lambda: tmp_path,
        )
        AppSettings._instances.clear()
        settings = get_settings()
        existing_key = "existing-signing-key"
        rotated_key = "rotated-secret"
        settings.api_auth_jwt_secret = existing_key
        settings.save()

        monkeypatch.setattr(
            "cogitus.cli.commands._import_optional_module",
            lambda _: SimpleNamespace(hash_password=lambda _: "stored-digest"),
        )
        monkeypatch.setattr(
            "cogitus.cli.commands.token_urlsafe",
            lambda _: rotated_key,
        )

        result = runner.invoke(
            app,
            [
                "api",
                "set-auth",
                "--username",
                "api-user",
                "--password",
                "secret-password",
                "--rotate-secret",
            ],
        )

        AppSettings._instances.clear()
        loaded = get_settings()

        assert result.exit_code == 0
        assert "JWT signing secret rotated." in result.output
        assert loaded.api_auth_jwt_secret == rotated_key

    def test_api_set_auth_rejects_blank_username(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """set-auth should reject empty usernames."""
        monkeypatch.setattr(
            "simple_toml_settings.settings.xdg_config_home",
            lambda: tmp_path,
        )
        AppSettings._instances.clear()
        monkeypatch.setattr(
            "cogitus.cli.commands._import_optional_module",
            lambda _: SimpleNamespace(hash_password=lambda _: "stored-digest"),
        )

        result = runner.invoke(
            app,
            [
                "api",
                "set-auth",
                "--username",
                "   ",
                "--password",
                "secret-password",
            ],
        )

        assert result.exit_code == 1
        assert "username cannot be empty" in result.output


class TestMCPCommands:
    """Tests for MCP token and serve commands."""

    def test_mcp_token_creates_secret_and_prints_bearer_token(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Token should create a secret if missing and print a bearer token."""
        monkeypatch.setattr(
            "simple_toml_settings.settings.xdg_config_home",
            lambda: tmp_path,
        )
        AppSettings._instances.clear()
        generated_key = "g" * 32
        monkeypatch.setattr(
            "cogitus.cli.commands.token_urlsafe",
            lambda _: generated_key,
        )

        result = runner.invoke(app, ["mcp", "token"])

        AppSettings._instances.clear()
        auth_settings = get_mcp_auth_settings()

        assert result.exit_code == 0
        assert result.output.startswith("Bearer ")
        assert auth_settings.jwt_secret == generated_key
        assert "mcp_auth_jwt_secret" not in (
            tmp_path / "cogitus" / "config.toml"
        ).read_text(
            encoding="utf-8",
        )

    def test_mcp_token_rotates_secret_and_invalidates_old_token(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--rotate-secret should replace the secret before issuing a token."""
        monkeypatch.setattr(
            "simple_toml_settings.settings.xdg_config_home",
            lambda: tmp_path,
        )
        AppSettings._instances.clear()
        settings = get_settings()
        auth_settings = get_mcp_auth_settings()
        auth_settings.jwt_secret = "o" * 32
        auth_settings.save()
        old_token = MCPAuthManager(
            settings,
            auth_settings,
        ).create_access_token()
        monkeypatch.setattr(
            "cogitus.cli.commands.token_urlsafe",
            lambda _: "n" * 32,
        )

        result = runner.invoke(app, ["mcp", "token", "--rotate-secret"])

        AppSettings._instances.clear()
        loaded = get_settings()
        loaded_auth = get_mcp_auth_settings()
        manager = MCPAuthManager(loaded, loaded_auth)

        assert result.exit_code == 0
        assert loaded_auth.jwt_secret == "n" * 32
        assert result.output.startswith("Bearer ")
        assert "Restart any running MCP servers" in result.output
        with pytest.raises(HTTPException):
            manager.decode_access_token(old_token)

    def test_mcp_serve_uses_uvicorn_factory(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Serve should invoke uvicorn with the MCP app factory."""
        monkeypatch.setattr(
            "simple_toml_settings.settings.xdg_config_home",
            lambda: tmp_path,
        )
        AppSettings._instances.clear()
        auth_settings = get_mcp_auth_settings()
        auth_settings.jwt_secret = "m" * 32
        auth_settings.save()
        monkeypatch.delenv(COGITUS_MCP_DB_PATH_ENV, raising=False)
        db_path = tmp_path / "cogitus-mcp.db"

        try:
            with patch("uvicorn.run") as mock_run:
                result = runner.invoke(
                    app,
                    [
                        "mcp",
                        "serve",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "9002",
                        "--reload",
                        "--db-path",
                        str(db_path),
                    ],
                )

            assert result.exit_code == 0
            assert os.environ[COGITUS_MCP_DB_PATH_ENV] == str(db_path)
            mock_run.assert_called_once_with(
                "cogitus.api.mcp:create_mcp_app",
                host="127.0.0.1",
                port=9002,
                reload=True,
                factory=True,
            )
        finally:
            monkeypatch.delenv(COGITUS_MCP_DB_PATH_ENV, raising=False)

    def test_mcp_serve_clears_db_path_env_when_not_provided(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Serve command should clear any prior MCP DB path override."""
        monkeypatch.setattr(
            "simple_toml_settings.settings.xdg_config_home",
            lambda: tmp_path,
        )
        AppSettings._instances.clear()
        auth_settings = get_mcp_auth_settings()
        auth_settings.jwt_secret = "m" * 32
        auth_settings.save()
        monkeypatch.setenv(COGITUS_MCP_DB_PATH_ENV, "stale-value")

        with patch("uvicorn.run") as mock_run:
            result = runner.invoke(app, ["mcp", "serve"])

        assert result.exit_code == 0
        assert COGITUS_MCP_DB_PATH_ENV not in os.environ
        mock_run.assert_called_once_with(
            "cogitus.api.mcp:create_mcp_app",
            host="127.0.0.1",
            port=9000,
            reload=False,
            factory=True,
        )

    def test_mcp_serve_requires_api_extra(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Serve command should fail cleanly without MCP server deps."""
        monkeypatch.setattr(
            "simple_toml_settings.settings.xdg_config_home",
            lambda: tmp_path,
        )
        AppSettings._instances.clear()
        auth_settings = get_mcp_auth_settings()
        auth_settings.jwt_secret = "m" * 32
        auth_settings.save()

        def fake_import_module(name: str) -> object:
            if name == "uvicorn":
                return SimpleNamespace(
                    run=lambda *_args, **_kwargs: pytest.fail(
                        "uvicorn.run should not be called"
                    )
                )
            if name == "cogitus.api.mcp":
                raise ModuleNotFoundError
            return __import__(name)

        monkeypatch.setattr(
            "cogitus.cli.commands.importlib.import_module",
            fake_import_module,
        )

        result = runner.invoke(app, ["mcp", "serve"])

        assert result.exit_code == 1
        assert "pip install cogitus[api]" in result.output

    def test_mcp_serve_requires_configured_secret(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Serve should fail clearly before uvicorn if no MCP secret exists."""
        monkeypatch.setattr(
            "simple_toml_settings.settings.xdg_config_home",
            lambda: tmp_path,
        )
        AppSettings._instances.clear()

        with patch("uvicorn.run") as mock_run:
            result = runner.invoke(app, ["mcp", "serve"])

        assert result.exit_code == 1
        assert "MCP authentication is not configured" in result.output
        assert not (tmp_path / "cogitus" / "mcp-auth.toml").exists()
        mock_run.assert_not_called()


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
            "Cogitus\n"
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

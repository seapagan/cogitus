"""Tests for application metadata helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import cogitus.metadata as metadata_module

if TYPE_CHECKING:
    from email.message import Message

    import pytest


class _FakePackageMetadata(dict[str, str]):
    """Metadata mapping with support for repeated Project-URL entries."""

    def __init__(
        self,
        *args: object,
        project_urls: list[str] | None = None,
        repeated_fields: dict[str, list[str]] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._repeated_fields = dict(repeated_fields or {})
        if project_urls is not None:
            self._repeated_fields["Project-URL"] = list(project_urls)

    def get_all(
        self,
        key: str,
        default: list[str] | None = None,
    ) -> list[str] | None:
        """Return repeated metadata values for the requested key."""
        return self._repeated_fields.get(key, default)


def test_get_app_metadata_reads_installed_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Metadata helper should read title, summary, and version."""
    monkeypatch.setattr(
        "cogitus.metadata.importlib_metadata.metadata",
        lambda _: _FakePackageMetadata(
            {
                "Name": "cogitus",
                "Summary": "Test summary",
                "Author": "Grant Ramsay",
                "Author-email": "Grant Ramsay <grant@example.com>",
                "License-Expression": "MIT",
            },
            project_urls=[
                "Homepage, https://example.com/docs",
                "Repository, https://example.com/repo",
                "Issues, https://example.com/issues",
            ],
            repeated_fields={"License-File": ["LICENSE.txt"]},
        ),
    )
    monkeypatch.setattr(
        "cogitus.metadata.importlib_metadata.version",
        lambda _: "1.2.3",
    )

    result = metadata_module.get_app_metadata()

    assert result == metadata_module.AppMetadata(
        title="Cogitus",
        version="1.2.3",
        summary="Test summary",
        author="Grant Ramsay",
        author_email="grant@example.com",
        project_urls={
            "Homepage": "https://example.com/docs",
            "Repository": "https://example.com/repo",
            "Issues": "https://example.com/issues",
        },
        license_name="MIT",
    )


def test_get_app_metadata_allows_missing_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Metadata helper should allow optional summary metadata."""
    monkeypatch.setattr(
        "cogitus.metadata.importlib_metadata.metadata",
        lambda _: _FakePackageMetadata({"Name": "cogitus"}),
    )
    monkeypatch.setattr(
        "cogitus.metadata.importlib_metadata.version",
        lambda _: "2.0.0",
    )

    result = metadata_module.get_app_metadata()

    assert result.summary is None
    assert result.author is None
    assert result.author_email is None
    assert result.project_urls == {}
    assert result.version == "2.0.0"


def test_get_app_metadata_falls_back_to_author_email_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Metadata helper should use Author-email when Author is absent."""
    monkeypatch.setattr(
        "cogitus.metadata.importlib_metadata.metadata",
        lambda _: _FakePackageMetadata(
            {
                "Name": "cogitus",
                "Author-email": "Grant Ramsay <grant@example.com>",
            },
        ),
    )
    monkeypatch.setattr(
        "cogitus.metadata.importlib_metadata.version",
        lambda _: "3.0.0",
    )

    result = metadata_module.get_app_metadata()

    assert result.author == "Grant Ramsay"
    assert result.author_email == "grant@example.com"


def test_parse_project_urls_ignores_malformed_entries() -> None:
    """Project URLs without a label separator should be ignored."""
    package_metadata = _FakePackageMetadata(
        project_urls=[
            "Malformed project url entry",
            "Repository, https://example.com/repo",
        ]
    )

    result = metadata_module._parse_project_urls(
        cast("Message", package_metadata)
    )

    assert result == {"Repository": "https://example.com/repo"}


def test_format_version_output_uses_fixed_layout() -> None:
    """Version output should render a readable metadata card."""
    app_metadata = metadata_module.AppMetadata(
        title="Cogitus",
        version="1.2.3",
        summary="Test summary",
    )

    result = metadata_module.format_version_output(app_metadata, year=2026)

    assert result == (
        "Cogitus\nTest summary\n© 2026 Grant Ramsay (seapagan)\nVersion: 1.2.3"
    )


def test_get_about_entries_uses_selected_metadata_fields() -> None:
    """About metadata rows should include curated runtime fields."""
    app_metadata = metadata_module.AppMetadata(
        title="Cogitus",
        version="1.2.3",
        summary="Test summary",
        author="Grant Ramsay",
        author_email="grant@example.com",
        project_urls={
            "Homepage": "https://example.com/docs",
            "Repository": "https://example.com/repo",
            "Issues": "https://example.com/issues",
            "Pull Requests": "https://example.com/pulls",
        },
        license_name="MIT",
    )

    result = metadata_module.get_about_entries(app_metadata)

    assert result == [
        ("Version", "1.2.3"),
        ("Author", "Grant Ramsay"),
        ("Repository", "https://example.com/repo"),
        ("Docs", "https://example.com/docs"),
        ("Issues", "https://example.com/issues"),
        ("License", "MIT"),
    ]


def test_get_about_entries_omits_missing_optional_fields() -> None:
    """About metadata rows should omit unavailable optional fields."""
    app_metadata = metadata_module.AppMetadata(
        title="Cogitus",
        version="1.2.3",
    )

    result = metadata_module.get_about_entries(app_metadata)

    assert result == [("Version", "1.2.3"), ("License", "MIT")]

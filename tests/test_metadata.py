"""Tests for application metadata helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import cogitus.metadata as metadata_module

if TYPE_CHECKING:
    import pytest


def test_get_app_metadata_reads_installed_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Metadata helper should read title, summary, and version."""
    monkeypatch.setattr(
        "cogitus.metadata.importlib_metadata.metadata",
        lambda _: {
            "Name": "cogitus",
            "Summary": "Test summary",
        },
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
    )


def test_get_app_metadata_allows_missing_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Metadata helper should allow optional summary metadata."""
    monkeypatch.setattr(
        "cogitus.metadata.importlib_metadata.metadata",
        lambda _: {"Name": "cogitus"},
    )
    monkeypatch.setattr(
        "cogitus.metadata.importlib_metadata.version",
        lambda _: "2.0.0",
    )

    result = metadata_module.get_app_metadata()

    assert result.summary is None
    assert result.version == "2.0.0"


def test_format_version_output_uses_fixed_layout() -> None:
    """Version output should render a readable metadata card."""
    app_metadata = metadata_module.AppMetadata(
        title="Cogitus",
        version="1.2.3",
        summary="Test summary",
    )

    result = metadata_module.format_version_output(app_metadata, year=2026)

    assert result == (
        "Test summary\n© 2026 Grant Ramsay (seapagan)\nVersion: 1.2.3"
    )

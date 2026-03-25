"""Application metadata helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from email.message import Message

DISTRIBUTION_NAME = "cogitus"
COPYRIGHT_HOLDER = "Grant Ramsay (seapagan)"


@dataclass(frozen=True, slots=True)
class AppMetadata:
    """Normalized metadata used by the CLI and TUI."""

    title: str
    version: str
    summary: str | None = None


def get_app_metadata(
    distribution_name: str = DISTRIBUTION_NAME,
) -> AppMetadata:
    """Load application metadata from the installed package metadata."""
    package_metadata = cast(
        "Message",
        importlib_metadata.metadata(distribution_name),
    )
    raw_name = package_metadata.get("Name", distribution_name).strip()
    title = raw_name[:1].upper() + raw_name[1:] if raw_name else "Cogitus"
    summary = package_metadata.get("Summary")
    version = importlib_metadata.version(distribution_name)
    return AppMetadata(title=title, version=version, summary=summary)


def format_version_output(
    app_metadata: AppMetadata,
    *,
    year: int | None = None,
) -> str:
    """Format the CLI version output."""
    resolved_year = datetime.now(tz=timezone.utc).year if year is None else year
    lines = [app_metadata.summary or app_metadata.title]
    lines.append(f"© {resolved_year} {COPYRIGHT_HOLDER}")
    lines.append(f"Version: {app_metadata.version}")
    return "\n".join(lines)

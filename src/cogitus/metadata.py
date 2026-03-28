"""Application metadata helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parseaddr
from importlib import metadata as importlib_metadata
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from email.message import Message

DISTRIBUTION_NAME = "cogitus"
COPYRIGHT_HOLDER = "Grant Ramsay (seapagan)"
DEFAULT_LICENSE_NAME = "MIT"
_ABOUT_PROJECT_URL_LABELS = (
    ("Repository", "Repository"),
    ("Homepage", "Docs"),
    ("Issues", "Issues"),
)


@dataclass(frozen=True, slots=True)
class AppMetadata:
    """Normalized metadata used by the CLI and TUI."""

    title: str
    version: str
    summary: str | None = None
    author: str | None = None
    author_email: str | None = None
    project_urls: dict[str, str] = field(default_factory=dict)
    license_name: str | None = None


def _get_repeated_metadata_values(
    package_metadata: Message,
    key: str,
) -> list[str]:
    """Return repeated metadata values for the requested key."""
    get_all = getattr(package_metadata, "get_all", None)
    return get_all(key, []) if callable(get_all) else []


def _clean_optional_text(value: str | None) -> str | None:
    """Return a stripped metadata value or None when it is blank."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _parse_project_urls(package_metadata: Message) -> dict[str, str]:
    """Normalize repeated Project-URL metadata entries into a mapping."""
    project_urls: dict[str, str] = {}

    for raw_value in _get_repeated_metadata_values(
        package_metadata, "Project-URL"
    ):
        label, separator, url = raw_value.partition(",")
        if not separator:
            continue
        clean_label = label.strip()
        clean_url = url.strip()
        if clean_label and clean_url:
            project_urls[clean_label] = clean_url

    return project_urls


def _resolve_license_name(package_metadata: Message) -> str | None:
    """Return the declared license label from package metadata."""
    return _clean_optional_text(
        package_metadata.get("License-Expression")
    ) or _clean_optional_text(package_metadata.get("License"))


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
    summary = _clean_optional_text(package_metadata.get("Summary"))
    raw_author = _clean_optional_text(package_metadata.get("Author"))
    raw_author_email = _clean_optional_text(
        package_metadata.get("Author-email")
    )
    parsed_author_name, parsed_author_email = parseaddr(raw_author_email or "")
    author = raw_author or _clean_optional_text(parsed_author_name)
    author_email = _clean_optional_text(parsed_author_email)
    version = importlib_metadata.version(distribution_name)
    license_name = _resolve_license_name(package_metadata)
    return AppMetadata(
        title=title,
        version=version,
        summary=summary,
        author=author,
        author_email=author_email,
        project_urls=_parse_project_urls(package_metadata),
        license_name=license_name,
    )


def format_version_output(
    app_metadata: AppMetadata,
    *,
    year: int | None = None,
) -> str:
    """Format the CLI version output."""
    resolved_year = datetime.now(tz=timezone.utc).year if year is None else year
    lines = [app_metadata.title]
    if app_metadata.summary:
        lines.append(app_metadata.summary)
    lines.append(f"© {resolved_year} {COPYRIGHT_HOLDER}")
    lines.append(f"Version: {app_metadata.version}")
    return "\n".join(lines)


def get_about_entries(app_metadata: AppMetadata) -> list[tuple[str, str]]:
    """Return ordered About dialog metadata rows."""
    lines: list[tuple[str, str]] = [("Version", app_metadata.version)]
    if app_metadata.author:
        lines.append(("Author", app_metadata.author))
    for project_url_label, display_label in _ABOUT_PROJECT_URL_LABELS:
        project_url = app_metadata.project_urls.get(project_url_label)
        if project_url:
            lines.append((display_label, project_url))
    lines.append(("License", app_metadata.license_name or DEFAULT_LICENSE_NAME))
    return lines

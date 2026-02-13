"""Output formatters for CLI commands."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from io import StringIO
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from cogitus.models.idea import Idea


def idea_to_dict(idea: Idea) -> dict[str, object]:
    """Convert an Idea model to a JSON-serializable dictionary.

    Args:
        idea: The Idea model instance.

    Returns:
        A dictionary with idea data including tags.
    """
    # Fetch tags from the many-to-many relationship
    tags = [tag.name for tag in idea.tags.fetch_all()]
    return {
        "pk": idea.pk,
        "title": idea.title,
        "body": idea.body,
        "group": idea.group.name,
        "group_pk": idea.group.pk,
        "tags": tags,
        "created_at": _format_timestamp(idea.created_at),
        "updated_at": _format_timestamp(idea.updated_at),
    }


def format_ideas_json(ideas: list[Idea]) -> str:
    """Format ideas as a JSON array.

    Args:
        ideas: List of Idea models.

    Returns:
        JSON string representation.
    """
    data = [idea_to_dict(idea) for idea in ideas]
    return json.dumps(data, indent=2)


def format_ideas_table(ideas: list[Idea]) -> str:
    """Format ideas as a Rich table.

    Args:
        ideas: List of Idea models.

    Returns:
        Table string.
    """
    if not ideas:
        return "No ideas found."

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Title", style="green")
    table.add_column("Group", style="yellow")
    table.add_column("Updated", style="dim")

    for idea in ideas:
        table.add_row(
            str(idea.pk),
            idea.title,
            idea.group.name,
            _format_short_date(idea.updated_at),
        )

    output = StringIO()
    console = Console(file=output)
    console.print(table)
    return output.getvalue().rstrip()


def format_ideas_simple(ideas: list[Idea]) -> str:
    """Format ideas as simple one-line entries.

    Args:
        ideas: List of Idea models.

    Returns:
        Simple format string with one idea per line.
    """
    if not ideas:
        return "No ideas found."

    lines = []
    for idea in ideas:
        tags = idea.tags.fetch_all()
        tag_str = " ".join(f"[{tag.name}]" for tag in tags)
        if tag_str:
            lines.append(f"[{idea.pk}] {idea.title} {tag_str}")
        else:
            lines.append(f"[{idea.pk}] {idea.title}")
    return "\n".join(lines)


def format_idea_markdown(idea: Idea) -> str:
    """Format a single idea as markdown.

    Args:
        idea: The Idea model instance.

    Returns:
        Markdown formatted string.
    """
    tags = idea.tags.fetch_all()
    tag_str = " ".join(f"`{tag.name}`" for tag in tags)

    lines = [f"# [{idea.pk}] {idea.title}"]
    if tag_str:
        lines.append(f"\nTags: {tag_str}")
    lines.append(f"\n{idea.body}")
    return "\n".join(lines)


def format_ideas_markdown(ideas: list[Idea]) -> str:
    """Format multiple ideas as a markdown document.

    Args:
        ideas: List of Idea models.

    Returns:
        Markdown document string.
    """
    if not ideas:
        return "No ideas found."

    sections = [format_idea_markdown(idea) for idea in ideas]
    return "\n\n---\n\n".join(sections)


def _format_timestamp(ts: int) -> str:
    """Convert Unix timestamp to ISO-like string.

    Args:
        ts: Unix timestamp in seconds.

    Returns:
        Formatted datetime string.
    """
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _format_short_date(ts: int) -> str:
    """Convert Unix timestamp to short date string.

    Args:
        ts: Unix timestamp in seconds.

    Returns:
        Short formatted datetime string.
    """
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M")

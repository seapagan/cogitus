"""Query parsing for advanced search operators."""

from __future__ import annotations

from dataclasses import dataclass
from shlex import split as shlex_split
from typing import Literal

FilterField = Literal["tag", "group"]
FilterConnector = Literal["and", "or"]
_SUPPORTED_FIELDS: tuple[FilterField, ...] = ("tag", "group")


@dataclass(frozen=True)
class SearchFilter:
    """Structured filter parsed from query text."""

    field: FilterField
    value: str


@dataclass(frozen=True)
class SearchQuery:
    """Normalized representation of parsed search query text."""

    text: str | None
    filters: tuple[SearchFilter, ...]
    connectors: tuple[FilterConnector, ...]


def parse_search_query(raw_query: str) -> SearchQuery:
    """Parse raw query text into typed free-text and structured filters.

    Rules:
        - Supports inline operators: ``tag:`` and ``group:``.
        - Supports explicit connectors ``and`` and ``or`` between filters.
        - Defaults to ``and`` when connectors are omitted.
        - Invalid operators degrade to free text.
    """
    tokens = _tokenize(raw_query)
    filters: list[SearchFilter] = []
    connectors: list[FilterConnector] = []
    text_tokens: list[str] = []
    pending_connector: FilterConnector | None = None

    for token in tokens:
        parsed_filter = _parse_filter(token)
        if parsed_filter is not None:
            if filters:
                connectors.append(pending_connector or "and")
            filters.append(parsed_filter)
            pending_connector = None
            continue

        connector = _as_connector(token)
        if connector is not None and filters:
            if pending_connector is not None:
                text_tokens.append(pending_connector)
            pending_connector = connector
            continue

        if pending_connector is not None:
            text_tokens.append(pending_connector)
            pending_connector = None
        text_tokens.append(token)

    if pending_connector is not None:
        text_tokens.append(pending_connector)

    text = " ".join(text_tokens).strip() or None
    return SearchQuery(
        text=text,
        filters=tuple(filters),
        connectors=tuple(connectors),
    )


def _tokenize(query: str) -> list[str]:
    """Tokenize query with quote support and resilient fallback."""
    try:
        return shlex_split(query)
    except ValueError:
        # Graceful fallback for malformed quotes.
        return query.split()


def _parse_filter(token: str) -> SearchFilter | None:
    """Return parsed filter for valid tokens, else None."""
    for field in _SUPPORTED_FIELDS:
        prefix = f"{field}:"
        if token.lower().startswith(prefix):
            value = token[len(prefix) :].strip().lower()
            if not value:
                return None
            return SearchFilter(field=field, value=value)
    return None


def _as_connector(token: str) -> FilterConnector | None:
    """Return normalized connector token if valid."""
    lowered = token.lower()
    if lowered == "and":
        return "and"
    if lowered == "or":
        return "or"
    return None

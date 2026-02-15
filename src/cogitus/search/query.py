"""Query parsing for advanced search operators."""

from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass
class _QueryParseState:
    """Mutable state used while parsing search tokens."""

    filters: list[SearchFilter] = field(default_factory=list)
    connectors: list[FilterConnector] = field(default_factory=list)
    text_tokens: list[str] = field(default_factory=list)
    pending_connector: FilterConnector | None = None


def parse_search_query(raw_query: str) -> SearchQuery:
    """Parse raw query text into typed free-text and structured filters.

    Rules:
        - Supports inline operators: ``tag:`` and ``group:``.
        - Supports explicit connectors ``and`` and ``or`` between filters.
        - Defaults to ``and`` when connectors are omitted.
        - Invalid operators degrade to free text.
    """
    state = _QueryParseState()
    for token in _tokenize(raw_query):
        _consume_token(token, state)
    _flush_pending_connector(state)

    text = " ".join(state.text_tokens).strip() or None
    return SearchQuery(
        text=text,
        filters=tuple(state.filters),
        connectors=tuple(state.connectors),
    )


def _consume_token(token: str, state: _QueryParseState) -> None:
    """Consume one token into parser state."""
    if _consume_filter_token(token, state):
        return
    if _consume_connector_token(token, state):
        return
    _consume_text_token(token, state)


def _consume_filter_token(token: str, state: _QueryParseState) -> bool:
    """Consume token as a structured filter if valid."""
    parsed_filter = _parse_filter(token)
    if parsed_filter is None:
        return False
    if state.filters:
        state.connectors.append(state.pending_connector or "and")
    state.filters.append(parsed_filter)
    state.pending_connector = None
    return True


def _consume_connector_token(token: str, state: _QueryParseState) -> bool:
    """Consume token as a filter connector if applicable."""
    connector = _as_connector(token)
    if connector is None or not state.filters:
        return False
    if state.pending_connector is not None:
        state.text_tokens.append(state.pending_connector)
    state.pending_connector = connector
    return True


def _consume_text_token(token: str, state: _QueryParseState) -> None:
    """Consume token as plain text and flush pending connector state."""
    _flush_pending_connector(state)
    state.text_tokens.append(token)


def _flush_pending_connector(state: _QueryParseState) -> None:
    """Flush pending connector into free-text tokens when needed."""
    if state.pending_connector is not None:
        state.text_tokens.append(state.pending_connector)
        state.pending_connector = None


def _tokenize(query: str) -> list[str]:
    """Tokenize query with quote support and resilient fallback."""
    try:
        return shlex_split(query)
    except ValueError:
        # Graceful fallback for malformed quotes.
        return query.split()


def _parse_filter(token: str) -> SearchFilter | None:
    """Return parsed filter for valid tokens, else None."""
    for filter_field in _SUPPORTED_FIELDS:
        prefix = f"{filter_field}:"
        if token.lower().startswith(prefix):
            value = token[len(prefix) :].strip().lower()
            if not value:
                return None
            return SearchFilter(field=filter_field, value=value)
    return None


def _as_connector(token: str) -> FilterConnector | None:
    """Return normalized connector token if valid."""
    lowered = token.lower()
    if lowered == "and":
        return "and"
    if lowered == "or":
        return "or"
    return None

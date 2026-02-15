"""Tests for advanced search query parsing."""

from __future__ import annotations

from cogitus.search import parse_search_query


def test_parse_plain_text_only() -> None:
    """Plain text should remain in the text clause."""
    parsed = parse_search_query("python async patterns")

    assert parsed.text == "python async patterns"
    assert parsed.filters == ()
    assert parsed.connectors == ()


def test_parse_structured_filters_with_implicit_and() -> None:
    """Adjacent filters without operators should default to AND."""
    parsed = parse_search_query("tag:python group:backend")

    assert parsed.text is None
    assert [item.field for item in parsed.filters] == ["tag", "group"]
    assert [item.value for item in parsed.filters] == ["python", "backend"]
    assert parsed.connectors == ("and",)


def test_parse_structured_filters_with_explicit_or() -> None:
    """Explicit OR should be preserved between filters."""
    parsed = parse_search_query("tag:python or tag:typescript")

    assert parsed.text is None
    assert [item.value for item in parsed.filters] == [
        "python",
        "typescript",
    ]
    assert parsed.connectors == ("or",)


def test_parse_mixed_text_and_filters() -> None:
    """Mixed free text and filters should populate both fields."""
    parsed = parse_search_query("api design tag:python and group:backend")

    assert parsed.text == "api design"
    assert [item.field for item in parsed.filters] == ["tag", "group"]
    assert parsed.connectors == ("and",)


def test_parse_invalid_operator_tokens_degrade_to_text() -> None:
    """Invalid operator tokens should remain plain text."""
    parsed = parse_search_query("tag: group: foo:bar")

    assert parsed.text == "tag: group: foo:bar"
    assert parsed.filters == ()
    assert parsed.connectors == ()


def test_parse_dangling_connector_degrades_to_text() -> None:
    """Dangling connector should be treated as text, not syntax error."""
    parsed = parse_search_query("tag:python and")

    assert parsed.text == "and"
    assert [item.value for item in parsed.filters] == ["python"]
    assert parsed.connectors == ()


def test_parse_quoted_filter_value() -> None:
    """Quoted filter values should be supported by shlex parsing."""
    parsed = parse_search_query('group:"backend api"')

    assert parsed.text is None
    assert [item.value for item in parsed.filters] == ["backend api"]
    assert parsed.connectors == ()


def test_parse_consecutive_connectors_preserves_previous_as_text() -> None:
    """A replaced pending connector should be retained as free text."""
    parsed = parse_search_query("tag:python and or tag:api")

    assert parsed.text == "and"
    assert [item.value for item in parsed.filters] == ["python", "api"]
    assert parsed.connectors == ("or",)


def test_parse_pending_connector_before_text_token() -> None:
    """Pending connector before plain text should degrade into text."""
    parsed = parse_search_query("tag:python and trailing")

    assert parsed.text == "and trailing"
    assert [item.value for item in parsed.filters] == ["python"]
    assert parsed.connectors == ()


def test_parse_malformed_quotes_falls_back_to_split() -> None:
    """Malformed quotes should use fallback tokenization."""
    parsed = parse_search_query('"unterminated')

    assert parsed.text == '"unterminated'
    assert parsed.filters == ()
    assert parsed.connectors == ()

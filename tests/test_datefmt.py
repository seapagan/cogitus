"""Tests for the cogitus.datefmt locale-aware date formatting module."""

from __future__ import annotations

import locale
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from cogitus.datefmt import (
    DateOrder,
    detect_locale_date_order,
    format_full_timestamp,
    format_relative_timestamp,
    resolve_date_order,
    resolve_timezone,
)


def _to_unix(dt: datetime) -> int:
    """Convert a datetime to a Unix timestamp."""
    return int(dt.timestamp())


# ---- detect_locale_date_order ----


def test_detect_locale_date_order_returns_iso_on_error() -> None:
    """Locale detection returns ISO when nl_langinfo is unavailable."""
    with patch.object(locale, "setlocale", side_effect=locale.Error):
        assert detect_locale_date_order() == DateOrder.ISO


def test_detect_locale_date_order_mdy() -> None:
    """Detect MDY order from a US-style locale format string."""
    with (
        patch.object(locale, "setlocale", return_value="en_US.UTF-8"),
        patch.object(locale, "nl_langinfo", return_value="%m/%d/%Y"),
    ):
        assert detect_locale_date_order() == DateOrder.MDY


def test_detect_locale_date_order_dmy() -> None:
    """Detect DMY order from a UK-style locale format string."""
    with (
        patch.object(locale, "setlocale", return_value="en_GB.UTF-8"),
        patch.object(locale, "nl_langinfo", return_value="%d/%m/%Y"),
    ):
        assert detect_locale_date_order() == DateOrder.DMY


def test_detect_locale_date_order_iso_when_starts_with_year() -> None:
    """Detect ISO order when the format string starts with %Y."""
    with (
        patch.object(locale, "setlocale", return_value="sv_SE.UTF-8"),
        patch.object(locale, "nl_langinfo", return_value="%Y-%m-%d"),
    ):
        assert detect_locale_date_order() == DateOrder.ISO


def test_detect_locale_date_order_iso_on_empty_fmt() -> None:
    """Return ISO when nl_langinfo returns an empty string."""
    with (
        patch.object(locale, "setlocale", return_value="C"),
        patch.object(locale, "nl_langinfo", return_value=""),
    ):
        assert detect_locale_date_order() == DateOrder.ISO


# ---- resolve_date_order ----


def test_resolve_date_order_override_iso() -> None:
    """Explicit ISO override takes precedence over locale."""
    assert resolve_date_order("iso") == DateOrder.ISO


def test_resolve_date_order_override_mdy() -> None:
    """Explicit MDY override takes precedence over locale."""
    assert resolve_date_order("mdy") == DateOrder.MDY


def test_resolve_date_order_override_dmy() -> None:
    """Explicit DMY override takes precedence over locale."""
    assert resolve_date_order("dmy") == DateOrder.DMY


def test_resolve_date_order_empty_falls_back_to_locale() -> None:
    """Empty string triggers locale detection."""
    with (
        patch.object(locale, "setlocale", return_value="en_GB.UTF-8"),
        patch.object(locale, "nl_langinfo", return_value="%d/%m/%Y"),
    ):
        assert resolve_date_order("") == DateOrder.DMY


def test_resolve_date_order_invalid_falls_back_to_locale() -> None:
    """Invalid override string triggers locale detection."""
    with (
        patch.object(locale, "setlocale", return_value="en_US.UTF-8"),
        patch.object(locale, "nl_langinfo", return_value="%m/%d/%Y"),
    ):
        assert resolve_date_order("nonsense") == DateOrder.MDY


def test_resolve_date_order_whitespace_stripped() -> None:
    """Whitespace is stripped before checking the override."""
    assert resolve_date_order("  dmy  ") == DateOrder.DMY


# ---- resolve_timezone ----


def test_resolve_timezone_explicit_zone() -> None:
    """Explicit IANA timezone name resolves correctly."""
    result = resolve_timezone("Europe/London")
    assert isinstance(result, ZoneInfo)
    assert str(result) == "Europe/London"


def test_resolve_timezone_explicit_utc() -> None:
    """Explicit UTC string resolves to a UTC tzinfo."""
    result = resolve_timezone("UTC")
    # ZoneInfo("UTC") and timezone.utc are different objects
    # but represent the same timezone.
    assert isinstance(result, ZoneInfo)
    assert str(result) == "UTC"


def test_resolve_timezone_empty_returns_system() -> None:
    """Empty string returns system local timezone."""
    result = resolve_timezone("")
    assert isinstance(result, (timezone, ZoneInfo))


def test_resolve_timezone_invalid_falls_back_to_system() -> None:
    """Invalid timezone string falls back to system local."""
    result = resolve_timezone("Invalid/Zone")
    assert isinstance(result, (timezone, ZoneInfo))


def test_resolve_timezone_whitespace_stripped() -> None:
    """Whitespace is stripped from the timezone override."""
    result = resolve_timezone("  Europe/London  ")
    assert isinstance(result, ZoneInfo)
    assert str(result) == "Europe/London"


# ---- format_full_timestamp ----


def test_format_full_timestamp_zero_returns_em_dash() -> None:
    """Unix timestamp 0 returns the em-dash placeholder."""
    assert (
        format_full_timestamp(0, tz=timezone.utc, date_order=DateOrder.ISO)
        == "\u2014"
    )


def test_format_full_timestamp_utc_iso() -> None:
    """UTC timezone with ISO order produces YYYY-MM-DD HH:MM UTC."""
    ts = _to_unix(datetime(2025, 2, 7, 14, 5, tzinfo=timezone.utc))
    result = format_full_timestamp(
        ts, tz=timezone.utc, date_order=DateOrder.ISO
    )
    assert result == "2025-02-07 14:05 UTC"


def test_format_full_timestamp_utc_dmy() -> None:
    """UTC timezone with DMY order produces DD/MM/YYYY HH:MM UTC."""
    ts = _to_unix(datetime(2025, 2, 7, 14, 5, tzinfo=timezone.utc))
    result = format_full_timestamp(
        ts, tz=timezone.utc, date_order=DateOrder.DMY
    )
    assert result == "07/02/2025 14:05 UTC"


def test_format_full_timestamp_utc_mdy() -> None:
    """UTC timezone with MDY order produces MM/DD/YYYY HH:MM UTC."""
    ts = _to_unix(datetime(2025, 2, 7, 14, 5, tzinfo=timezone.utc))
    result = format_full_timestamp(
        ts, tz=timezone.utc, date_order=DateOrder.MDY
    )
    assert result == "02/07/2025 14:05 UTC"


def test_format_full_timestamp_local_tz_shows_abbr() -> None:
    """Local timezone shows its abbreviation in the output."""
    ts = _to_unix(datetime(2025, 2, 7, 14, 5, tzinfo=timezone.utc))
    tz = ZoneInfo("Europe/London")
    result = format_full_timestamp(ts, tz=tz, date_order=DateOrder.DMY)
    # Winter time in London is GMT
    assert result == "07/02/2025 14:05 GMT"


def test_format_full_timestamp_dst_tz_shows_abbr() -> None:
    """DST timezone shows the DST abbreviation."""
    ts = _to_unix(datetime(2025, 7, 7, 14, 5, tzinfo=timezone.utc))
    tz = ZoneInfo("Europe/London")
    result = format_full_timestamp(ts, tz=tz, date_order=DateOrder.DMY)
    assert result == "07/07/2025 15:05 BST"


def test_format_full_timestamp_negative_offset_zone() -> None:
    """Negative offset timezone shifts the date correctly."""
    ts = _to_unix(datetime(2025, 2, 7, 23, 30, tzinfo=timezone.utc))
    tz = ZoneInfo("America/New_York")
    result = format_full_timestamp(ts, tz=tz, date_order=DateOrder.MDY)
    assert result == "02/07/2025 18:30 EST"


# ---- format_relative_timestamp ----


def test_format_relative_timestamp_zero_returns_empty() -> None:
    """Unix timestamp 0 returns empty string."""
    assert (
        format_relative_timestamp(0, tz=timezone.utc, date_order=DateOrder.ISO)
        == ""
    )


def test_format_relative_timestamp_just_now() -> None:
    """Current time returns 'just now'."""
    now = datetime.now(tz=timezone.utc)
    result = format_relative_timestamp(
        _to_unix(now), tz=timezone.utc, date_order=DateOrder.ISO
    )
    assert result == "just now"


def test_format_relative_timestamp_minutes_ago() -> None:
    """Two minutes ago returns '2m ago'."""
    now = datetime.now(tz=timezone.utc)
    result = format_relative_timestamp(
        _to_unix(now - timedelta(minutes=2)),
        tz=timezone.utc,
        date_order=DateOrder.ISO,
    )
    assert result == "2m ago"


def test_format_relative_timestamp_hours_ago() -> None:
    """Two hours ago returns '2h ago'."""
    now = datetime.now(tz=timezone.utc)
    result = format_relative_timestamp(
        _to_unix(now - timedelta(hours=2)),
        tz=timezone.utc,
        date_order=DateOrder.ISO,
    )
    assert result == "2h ago"


def test_format_relative_timestamp_yesterday() -> None:
    """One day ago returns 'yesterday'."""
    now = datetime.now(tz=timezone.utc)
    result = format_relative_timestamp(
        _to_unix(now - timedelta(days=1)),
        tz=timezone.utc,
        date_order=DateOrder.ISO,
    )
    assert result == "yesterday"


def test_format_relative_timestamp_days_ago() -> None:
    """Three days ago returns '3d ago'."""
    now = datetime.now(tz=timezone.utc)
    result = format_relative_timestamp(
        _to_unix(now - timedelta(days=3)),
        tz=timezone.utc,
        date_order=DateOrder.ISO,
    )
    assert result == "3d ago"


def test_format_relative_timestamp_absolute_fallback_iso() -> None:
    """Older than 7 days uses ISO date format."""
    now = datetime.now(tz=timezone.utc)
    older = now - timedelta(days=10)
    result = format_relative_timestamp(
        _to_unix(older), tz=timezone.utc, date_order=DateOrder.ISO
    )
    assert result == older.strftime("%Y-%m-%d")


def test_format_relative_timestamp_absolute_fallback_dmy() -> None:
    """Older than 7 days uses DMY date format."""
    now = datetime.now(tz=timezone.utc)
    older = now - timedelta(days=10)
    result = format_relative_timestamp(
        _to_unix(older), tz=timezone.utc, date_order=DateOrder.DMY
    )
    assert result == older.strftime("%d/%m/%Y")


def test_format_relative_timestamp_absolute_fallback_local_tz() -> None:
    """Absolute fallback converts to the local timezone."""
    # 2025-02-07 23:30 UTC = 2025-02-07 18:30 EST
    ts = _to_unix(datetime(2025, 2, 7, 23, 30, tzinfo=timezone.utc))
    tz = ZoneInfo("America/New_York")
    now = datetime.now(tz=timezone.utc)
    # Ensure this is "old enough" (>7 days)
    assert now - datetime.fromtimestamp(ts, tz=timezone.utc) > timedelta(days=7)
    result = format_relative_timestamp(ts, tz=tz, date_order=DateOrder.MDY)
    assert result == "02/07/2025"

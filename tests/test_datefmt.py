"""Tests for the cogitus.datefmt locale-aware date formatting module."""

from __future__ import annotations

import locale
from datetime import datetime, timedelta, timezone, tzinfo
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from cogitus.config import is_valid_date_format, is_valid_timezone
from cogitus.datefmt import (
    DateOrder,
    _tz_abbr,
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
    """Locale detection returns ISO when setlocale raises."""
    with patch.object(locale, "setlocale", side_effect=locale.Error):
        assert detect_locale_date_order() == DateOrder.ISO


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [
        ("%m/%d/%Y", DateOrder.MDY),
        ("%d/%m/%Y", DateOrder.DMY),
        ("%e/%m/%Y", DateOrder.DMY),
        ("%-m/%-d/%Y", DateOrder.MDY),
        ("%_d.%_m.%Y", DateOrder.DMY),
        ("%Y-%m-%d", DateOrder.ISO),
        ("", DateOrder.ISO),
    ],
    ids=[
        "mdy",
        "dmy",
        "dmy-percent-e",
        "mdy-flag-minus",
        "dmy-flag-underscore",
        "iso-year-first",
        "iso-empty-fmt",
    ],
)
def test_detect_locale_date_order(fmt: str, expected: DateOrder) -> None:
    """Detect date ordering from various locale D_FMT values."""
    with (
        patch.object(
            locale,
            "setlocale",
            side_effect=["C", "C", "C"],
        ),
        patch.object(
            locale,
            "nl_langinfo",
            return_value=fmt,
            create=True,
        ),
    ):
        assert detect_locale_date_order() == expected


# ---- resolve_date_order ----


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ("iso", DateOrder.ISO),
        ("mdy", DateOrder.MDY),
        ("dmy", DateOrder.DMY),
        ("  dmy  ", DateOrder.DMY),
    ],
    ids=["iso", "mdy", "dmy", "whitespace-stripped"],
)
def test_resolve_date_order_override(
    override: str, expected: DateOrder
) -> None:
    """Explicit override takes precedence over locale."""
    assert resolve_date_order(override) == expected


@pytest.mark.parametrize(
    ("override", "fmt", "expected"),
    [
        ("", "%d/%m/%Y", DateOrder.DMY),
        ("nonsense", "%m/%d/%Y", DateOrder.MDY),
    ],
    ids=["empty-falls-back", "invalid-falls-back"],
)
def test_resolve_date_order_falls_back_to_locale(
    override: str, fmt: str, expected: DateOrder
) -> None:
    """Empty or invalid override triggers locale detection."""
    with (
        patch.object(
            locale,
            "setlocale",
            side_effect=["C", "C", "C"],
        ),
        patch.object(
            locale,
            "nl_langinfo",
            return_value=fmt,
            create=True,
        ),
    ):
        assert resolve_date_order(override) == expected


# ---- resolve_timezone ----


def test_resolve_timezone_explicit_zone() -> None:
    """Explicit IANA timezone name resolves correctly."""
    result = resolve_timezone("Europe/London")
    assert isinstance(result, ZoneInfo)
    assert str(result) == "Europe/London"


def test_resolve_timezone_explicit_utc() -> None:
    """Explicit UTC string resolves to a UTC tzinfo."""
    result = resolve_timezone("UTC")
    assert isinstance(result, ZoneInfo)
    assert str(result) == "UTC"


def test_resolve_timezone_empty_returns_system() -> None:
    """Empty string returns system local timezone."""
    result = resolve_timezone("")
    assert isinstance(result, tzinfo)


def test_resolve_timezone_invalid_falls_back_to_system() -> None:
    """Invalid timezone string falls back to system local."""
    result = resolve_timezone("Invalid/Zone")
    assert isinstance(result, tzinfo)


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


_FROZEN_NOW = datetime(2025, 2, 8, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (timedelta(0), "just now"),
        (timedelta(minutes=2), "2m ago"),
        (timedelta(hours=2), "2h ago"),
        (timedelta(days=1), "yesterday"),
        (timedelta(days=3), "3d ago"),
    ],
    ids=["just-now", "minutes", "hours", "yesterday", "days"],
)
def test_format_relative_timestamp_branches(
    offset: timedelta, expected: str
) -> None:
    """Relative labels use frozen clock to avoid wall-clock flakiness."""
    ts = _to_unix(_FROZEN_NOW - offset)
    with patch("cogitus.datefmt.datetime") as mock_dt:
        mock_dt.now.return_value = _FROZEN_NOW
        mock_dt.fromtimestamp.side_effect = datetime.fromtimestamp
        result = format_relative_timestamp(
            ts, tz=timezone.utc, date_order=DateOrder.ISO
        )
    assert result == expected


@pytest.mark.parametrize(
    ("order", "expected"),
    [
        (DateOrder.ISO, "2025-01-29"),
        (DateOrder.DMY, "29/01/2025"),
    ],
    ids=["iso", "dmy"],
)
def test_format_relative_timestamp_absolute_fallback(
    order: DateOrder, expected: str
) -> None:
    """Older than 7 days uses regional date format."""
    older = _FROZEN_NOW - timedelta(days=10)
    ts = _to_unix(older)
    with patch("cogitus.datefmt.datetime") as mock_dt:
        mock_dt.now.return_value = _FROZEN_NOW
        mock_dt.fromtimestamp.side_effect = datetime.fromtimestamp
        result = format_relative_timestamp(
            ts, tz=timezone.utc, date_order=order
        )
    assert result == expected


def test_format_relative_timestamp_absolute_fallback_local_tz() -> None:
    """Absolute fallback converts to the local timezone."""
    ts = _to_unix(datetime(2025, 1, 28, 23, 30, tzinfo=timezone.utc))
    tz = ZoneInfo("America/New_York")
    with patch("cogitus.datefmt.datetime") as mock_dt:
        mock_dt.now.return_value = _FROZEN_NOW
        mock_dt.fromtimestamp.side_effect = datetime.fromtimestamp
        result = format_relative_timestamp(ts, tz=tz, date_order=DateOrder.MDY)
    assert result == "01/28/2025"


def test_format_relative_timestamp_yesterday_respects_local_tz() -> None:
    """Near midnight UTC, 'yesterday' uses local timezone day boundary.

    Item at 2025-02-08 00:30 UTC. In America/New_York that is
    2025-02-07 19:30 EST. Current time 2025-02-08 02:00 UTC = Feb 7
    21:00 EST. Same local date, so should be '1h ago' not
    'yesterday'.
    """
    tz = ZoneInfo("America/New_York")
    ts = _to_unix(datetime(2025, 2, 8, 0, 30, tzinfo=timezone.utc))
    now = datetime(2025, 2, 8, 2, 0, tzinfo=timezone.utc)
    with patch("cogitus.datefmt.datetime") as mock_dt:
        mock_dt.now.return_value = now.astimezone(tz)
        mock_dt.fromtimestamp.return_value = datetime.fromtimestamp(ts, tz=tz)
        result = format_relative_timestamp(ts, tz=tz, date_order=DateOrder.ISO)
    assert result == "1h ago"


def test_format_relative_timestamp_same_utc_day_different_local_day() -> None:
    """Different local day should show 'yesterday' even within 24h.

    Item at 2025-02-08 04:00 UTC. In America/New_York that is
    2025-02-07 23:00 EST. Current time 2025-02-08 05:00 UTC = Feb 8
    00:00 EST. Item is local-date Feb 7, now is local-date Feb 8, so
    'yesterday' is correct despite being only 1h apart.
    """
    tz = ZoneInfo("America/New_York")
    ts = _to_unix(datetime(2025, 2, 8, 4, 0, tzinfo=timezone.utc))
    now = datetime(2025, 2, 8, 5, 0, tzinfo=timezone.utc)
    with patch("cogitus.datefmt.datetime") as mock_dt:
        mock_dt.now.return_value = now.astimezone(tz)
        mock_dt.fromtimestamp.return_value = datetime.fromtimestamp(ts, tz=tz)
        result = format_relative_timestamp(ts, tz=tz, date_order=DateOrder.ISO)
    assert result == "yesterday"


# ---- resolve_timezone edge cases ----


def test_resolve_timezone_falls_back_to_utc_on_system_error() -> None:
    """Return UTC when system tz detection raises."""
    with patch("cogitus.datefmt.datetime") as mock_dt:
        mock_dt.now.side_effect = OSError("no tz")
        result = resolve_timezone("")
    assert result == timezone.utc


# ---- _tz_abbr edge cases ----


class _OffsetOnlyTz(tzinfo):
    """A tzinfo with an offset but no abbreviation name."""

    def utcoffset(self, _dt: datetime | None = None) -> timedelta:
        """Return a fixed +05:30 offset."""
        return timedelta(hours=5, minutes=30)

    def dst(self, _dt: datetime | None = None) -> timedelta | None:
        """No DST."""
        return timedelta(0)

    def tzname(self, _dt: datetime | None = None) -> str | None:
        """Return no abbreviation to trigger the fallback path."""
        return None


class _NoInfoTz(tzinfo):
    """A tzinfo with neither offset nor abbreviation."""

    def utcoffset(self, _dt: datetime | None = None) -> timedelta | None:
        """Return None to trigger full fallback."""
        return None

    def dst(self, _dt: datetime | None = None) -> timedelta | None:
        """No DST."""
        return None

    def tzname(self, _dt: datetime | None = None) -> str | None:
        """Return no abbreviation."""
        return None


def test_tz_abbr_uses_offset_when_abbr_empty() -> None:
    """When %Z is empty, format the UTC offset instead."""
    dt = datetime(2025, 1, 1, 12, 0, tzinfo=_OffsetOnlyTz())
    result = _tz_abbr(dt)
    assert result == "UTC+05:30"


def test_tz_abbr_returns_utc_when_both_empty() -> None:
    """When both %Z and %z are empty, return 'UTC'."""
    dt = datetime(2025, 1, 1, 12, 0, tzinfo=_NoInfoTz())
    result = _tz_abbr(dt)
    assert result == "UTC"


# ---- config validators ----


def test_is_valid_timezone_accepts_iana_name() -> None:
    """Valid IANA timezone name returns True."""
    assert is_valid_timezone("Europe/London") is True


def test_is_valid_timezone_rejects_invalid() -> None:
    """Invalid timezone string returns False."""
    assert is_valid_timezone("Not/ARealZone") is False


def test_is_valid_timezone_rejects_malformed() -> None:
    """Malformed timezone string (raises ValueError) returns False."""
    assert is_valid_timezone("America/../New_York") is False


def test_is_valid_timezone_accepts_empty() -> None:
    """Empty string is valid (means auto-detect)."""
    assert is_valid_timezone("") is True


def test_is_valid_date_format_accepts_known_values() -> None:
    """Known format strings return True."""
    for value in ("", "iso", "mdy", "dmy"):
        assert is_valid_date_format(value) is True


def test_is_valid_date_format_rejects_unknown() -> None:
    """Unknown format string returns False."""
    assert is_valid_date_format("ymd") is False

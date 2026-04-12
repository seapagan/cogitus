"""Locale-aware date/time formatting for display."""

from __future__ import annotations

import locale
from datetime import datetime, timezone, tzinfo
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_DAYS_IN_WEEK = 7


class DateOrder(str, Enum):
    """Supported date component ordering patterns."""

    ISO = "iso"  # YYYY-MM-DD
    MDY = "mdy"  # MM/DD/YYYY (US)
    DMY = "dmy"  # DD/MM/YYYY (UK/EU)


_VALID_DATE_ORDERS: frozenset[DateOrder] = frozenset(DateOrder)

_DATE_FMT: dict[DateOrder, str] = {
    DateOrder.ISO: "%Y-%m-%d",
    DateOrder.MDY: "%m/%d/%Y",
    DateOrder.DMY: "%d/%m/%Y",
}


def detect_locale_date_order() -> DateOrder:
    """Detect date ordering from the system locale.

    Falls back to ISO when locale information is unavailable
    or cannot be parsed.
    """
    try:
        locale.setlocale(locale.LC_TIME, "")
        fmt = locale.nl_langinfo(locale.D_FMT)
    except (locale.Error, AttributeError, ValueError):
        return DateOrder.ISO
    if not fmt:
        return DateOrder.ISO
    if fmt.startswith("%m"):
        return DateOrder.MDY
    if fmt.startswith("%d"):
        return DateOrder.DMY
    return DateOrder.ISO


def resolve_date_order(override: str = "") -> DateOrder:
    """Resolve date ordering from an optional override or locale.

    Args:
        override: Explicit value from settings ("" for auto-detect).

    Returns:
        The resolved DateOrder.
    """
    stripped = override.strip().lower()
    if stripped in _VALID_DATE_ORDERS:
        return DateOrder(stripped)
    return detect_locale_date_order()


def resolve_timezone(override: str = "") -> tzinfo:
    """Resolve the display timezone from an optional override or system.

    Args:
        override: IANA timezone name from settings ("" for system local).

    Returns:
        A tzinfo for the display timezone. Falls back to UTC when
        neither the override nor system detection succeeds.
    """
    stripped = override.strip()
    if stripped:
        try:
            return ZoneInfo(stripped)
        except ZoneInfoNotFoundError:
            pass
    try:
        local_tz = datetime.now().astimezone().tzinfo
        if local_tz is not None:
            return local_tz
    except (OSError, ValueError):
        pass
    return timezone.utc


def _tz_abbr(dt: datetime) -> str:
    """Return the timezone abbreviation, falling back to UTC offset."""
    abbr = dt.strftime("%Z")
    if abbr:
        return abbr
    offset = dt.strftime("%z")
    if offset:
        return f"UTC{offset[:3]}:{offset[3:]}"
    return "UTC"


def format_full_timestamp(
    unix_ts: int,
    *,
    tz: tzinfo,
    date_order: DateOrder,
) -> str:
    """Format a Unix timestamp as a full regional date-time string.

    Args:
        unix_ts: Unix timestamp in seconds (0 for placeholder).
        tz: Display timezone.
        date_order: Regional date component ordering.

    Returns:
        Formatted string like ``07/02/2025 14:05 GMT``, or an em-dash
        when ``unix_ts`` is 0.
    """
    if unix_ts == 0:
        return "\u2014"
    dt = datetime.fromtimestamp(unix_ts, tz=tz)
    date_part = dt.strftime(_DATE_FMT[date_order])
    return f"{date_part} {dt:%H:%M} {_tz_abbr(dt)}"


def format_relative_timestamp(
    unix_ts: int,
    *,
    tz: tzinfo,
    date_order: DateOrder,
) -> str:
    """Format a Unix timestamp as a relative or regional date string.

    Produces relative labels (``just now``, ``5m ago``, ``2h ago``,
    ``yesterday``, ``3d ago``) for recent timestamps. Falls back to a
    regional short date for anything older than one week.

    Args:
        unix_ts: Unix timestamp in seconds (0 returns empty string).
        tz: Display timezone (used for the absolute-date fallback).
        date_order: Regional date component ordering.

    Returns:
        A human-friendly timestamp string.
    """
    if unix_ts == 0:
        return ""
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    delta = now - dt
    if delta.days == 0:
        hours = delta.seconds // 3600
        if hours == 0:
            minutes = delta.seconds // 60
            return "just now" if minutes == 0 else f"{minutes}m ago"
        return f"{hours}h ago"
    if delta.days == 1:
        return "yesterday"
    if delta.days < _DAYS_IN_WEEK:
        return f"{delta.days}d ago"
    local_dt = datetime.fromtimestamp(unix_ts, tz=tz)
    return local_dt.strftime(_DATE_FMT[date_order])

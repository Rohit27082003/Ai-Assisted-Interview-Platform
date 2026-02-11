"""Datetime parsing utilities for consistent ISO 8601 handling."""

from datetime import datetime, timezone


def parse_iso_datetime(value) -> datetime:
    """
    Parse an ISO 8601 datetime string to a timezone-aware datetime.

    Handles:
    - String values with 'Z' suffix (JavaScript-style)
    - String values without timezone info (assumed UTC)
    - Already-parsed datetime objects (returned as-is, but made tz-aware)

    Args:
        value: ISO 8601 string or datetime object

    Returns:
        Timezone-aware datetime in UTC
    """
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        dt = value

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt

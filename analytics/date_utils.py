"""
Date Utilities for Timezone-Aware Date Range Parsing

This module provides a centralized utility for parsing date range parameters
with timezone support. All analytics and conversion views should use these
functions to ensure consistent date handling across the application.

The key insight: Users select dates in their local timezone (e.g., "Today" means
their local day), but the database stores timestamps in UTC. This module bridges
that gap by converting user's local date ranges to UTC boundaries.

Example:
    User in Stockholm (UTC+1) at 00:50 local time on Dec 19 clicks "Today".
    - Local "Today" = Dec 19, 00:00 → Dec 19, 23:59 (Stockholm time)
    - In UTC = Dec 18, 23:00 → Dec 19, 22:59
    - Database query should filter: timestamp >= Dec 18 23:00 UTC AND timestamp <= Dec 19 22:59 UTC

Usage:
    from analytics.date_utils import parse_date_range

    # In your view:
    tz_name = request.query_params.get('tz', 'UTC')
    from_datetime, to_datetime = parse_date_range(from_date_str, to_date_str, tz_name)

    if from_datetime:
        events = events.filter(timestamp__gte=from_datetime)
    if to_datetime:
        events = events.filter(timestamp__lte=to_datetime)
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)


def parse_date_range(
    from_date_str: str | None,
    to_date_str: str | None,
    tz_name: str = 'UTC'
) -> tuple[datetime | None, datetime | None]:
    """
    Parse date range parameters with timezone support.

    Converts user-provided date strings (in their local timezone) to
    timezone-aware UTC datetimes for database queries.

    Args:
        from_date_str: Start date string (YYYY-MM-DD) or None
        to_date_str: End date string (YYYY-MM-DD) or None
        tz_name: IANA timezone name (e.g., 'America/New_York', 'Europe/Stockholm').
                 Defaults to 'UTC'. Invalid timezone names silently fall back to UTC.

    Returns:
        Tuple of (from_datetime, to_datetime):
        - from_datetime: Start of from_date in user's timezone, converted to UTC
        - to_datetime: End of to_date (23:59:59.999999) in user's timezone, converted to UTC

    Raises:
        ValueError: If date format is invalid (not YYYY-MM-DD)

    Examples:
        >>> # User in New York selects Dec 19, 2025
        >>> from_dt, to_dt = parse_date_range('2025-12-19', '2025-12-19', 'America/New_York')
        >>> # from_dt = 2025-12-19 05:00:00 UTC (midnight EST)
        >>> # to_dt = 2025-12-20 04:59:59.999999 UTC (end of day EST)

        >>> # With invalid timezone, falls back to UTC
        >>> from_dt, to_dt = parse_date_range('2025-12-19', '2025-12-19', 'Invalid/Zone')
        >>> # Uses UTC, logs a warning
    """
    # Get user timezone, fall back to UTC if invalid
    user_tz = _get_timezone_safe(tz_name)

    from_datetime = None
    to_datetime = None

    if from_date_str:
        # Parse as start of day (00:00:00) in user's timezone
        naive_from = datetime.strptime(from_date_str, '%Y-%m-%d')
        local_from = naive_from.replace(tzinfo=user_tz)
        # Convert to UTC for database query
        from_datetime = local_from.astimezone(ZoneInfo('UTC'))

    if to_date_str:
        # Parse as end of day (23:59:59.999999) in user's timezone
        naive_to = datetime.strptime(to_date_str, '%Y-%m-%d')
        naive_to = naive_to.replace(hour=23, minute=59, second=59, microsecond=999999)
        local_to = naive_to.replace(tzinfo=user_tz)
        # Convert to UTC for database query
        to_datetime = local_to.astimezone(ZoneInfo('UTC'))

    return from_datetime, to_datetime


def _get_timezone_safe(tz_name: str) -> ZoneInfo:
    """
    Get a ZoneInfo object, falling back to UTC if the timezone is invalid.

    Args:
        tz_name: IANA timezone name (e.g., 'America/New_York')

    Returns:
        ZoneInfo object for the timezone, or UTC if invalid
    """
    if not tz_name:
        return ZoneInfo('UTC')

    try:
        return ZoneInfo(tz_name)
    except Exception as e:
        # Log the invalid timezone but don't fail the request
        logger.warning(f"Invalid timezone '{tz_name}', falling back to UTC: {e}")
        return ZoneInfo('UTC')


def get_cache_key_with_timezone(
    prefix: str,
    app_id: str,
    from_date: str | None,
    to_date: str | None,
    tz_name: str = 'UTC',
    **extra_params
) -> str:
    """
    Generate a cache key that includes timezone information.

    This ensures that cached results are timezone-specific, preventing
    users in different timezones from seeing each other's cached data.

    Args:
        prefix: Cache key prefix (e.g., 'summary', 'dau', 'funnel')
        app_id: UUID of the app
        from_date: Start date string or None
        to_date: End date string or None
        tz_name: User's timezone name (defaults to 'UTC')
        **extra_params: Additional parameters to include in the cache key

    Returns:
        Cache key string

    Examples:
        >>> get_cache_key_with_timezone('summary', 'abc-123', '2025-12-19', '2025-12-19', 'America/New_York')
        'summary:abc-123:2025-12-19:2025-12-19:America/New_York'

        >>> get_cache_key_with_timezone('funnel', 'abc-123', None, None, 'UTC', steps='a,b,c')
        'funnel:abc-123:all:all:UTC:steps=a,b,c'
    """
    # Normalize timezone name for consistent cache keys
    normalized_tz = tz_name if tz_name else 'UTC'

    # Build base key
    parts = [
        prefix,
        str(app_id),
        from_date or 'all',
        to_date or 'all',
        normalized_tz
    ]

    # Add extra parameters in sorted order for consistency
    if extra_params:
        sorted_params = sorted(extra_params.items())
        parts.extend([f"{k}={v}" for k, v in sorted_params if v is not None])

    return ':'.join(parts)


def format_date_for_response(dt: datetime | None) -> str | None:
    """
    Format a datetime for API response (YYYY-MM-DD format).

    Args:
        dt: datetime object or None

    Returns:
        Date string in YYYY-MM-DD format, or None if input is None
    """
    if dt is None:
        return None
    return dt.strftime('%Y-%m-%d')

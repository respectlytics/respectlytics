"""
Conversion Intelligence Views

Session-based analytics endpoints for understanding conversion patterns.
All views provide per-session analysis only (no cross-session tracking).

Available Endpoints:
- DAUView: Daily/Weekly/Monthly Active Sessions
- ConversionSummaryView: Conversion counts and rates
- TimeToConversionView: Time-to-conversion analysis
- StepTimingView: Funnel step timing analysis
- ConversionPathsView: Auto-discovered conversion paths
- DropOffView: Session drop-off diagnostics
- EventCorrelationView: Conversion drivers analysis
- SegmentComparisonView: Platform/country comparisons
- GlobeStatsView: Geographic visualization stats

Note: ConversionSignalsView was removed in v2.0.0 because it required
cross-session user tracking, which is not compatible with session-based analytics.
"""

import logging
import re
from collections import defaultdict
from datetime import timedelta
from functools import partial

from dateutil.relativedelta import relativedelta
from django.db.models import Count
from django.db.models.functions import TruncDay, TruncMonth, TruncQuarter, TruncWeek, TruncYear
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics import event_groups
from analytics.authentication import APP_OWNER
from analytics.base_events import base_events, session_count, sessions_per, slices_in
from analytics.date_utils import (
    _get_timezone_safe,
    default_range,
    freshness_mark,
    get_cache_key_with_timezone,
    parse_date_range,
)

# Import from analytics app (shared models, auth, permissions)
from analytics.intake import platform_name
from analytics.models import Event
from analytics.permissions import HasValidAppKey

logger = logging.getLogger(__name__)

# A declared property's name (properties/models.py NAME), and the row its rare values share
PROPERTY_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
MIN_PROPERTY_SESSIONS = 5
OTHER_VALUES = "Other values"


def _properties_included(app):
    """Whether the app may be compared by its declared properties: on respectlytics.com while
    its plan includes them (billing/features.py); elsewhere nothing declares any."""
    from django.apps import apps

    if not apps.is_installed("properties"):
        return True
    from billing import features

    return features.for_app(app, "properties")


# The dashboard reads events through the app's groups; an API caller who never asks keeps
# reading every event by its own name (analytics/event_groups.py).
GROUP_EVENTS = openapi.Parameter(
    "group_events",
    openapi.IN_QUERY,
    description=(
        "true reads every event as its event group, the way the dashboard shows it "
        "(purchase_light and purchase_pro as purchase), and lets a group's name stand for its "
        "events. Default false."
    ),
    type=openapi.TYPE_BOOLEAN,
)


class DAUView(APIView):
    """
    GET /api/v1/analytics/dau/ - Get Daily/Weekly/Monthly Active Sessions

    Returns unique sessions per period with flexible granularity for viewing
    trends at different time scales. Also includes average session length metrics.

    Query parameters:
        - from: Start date (YYYY-MM-DD)
        - to: End date (YYYY-MM-DD)
        - granularity: Time period grouping (day, week, month, quarter, year). Default: day

    Session Length Notes:
        - Calculated as time between first and last event in a session
        - Single-event sessions excluded (no meaningful duration)
        - Durations capped at 2 hours (session rotation edge cases)

    This is a session-based analysis - each session is a distinct app usage period
    (maximum 2 hours). Sessions are not tracked across app restarts.
    """

    share_links = True  # a share link's dashboard reads it (teams/)
    authentication_classes = APP_OWNER
    permission_classes = [HasValidAppKey]

    # Valid granularity options
    VALID_GRANULARITIES = ("day", "week", "month", "quarter", "year")

    @swagger_auto_schema(
        operation_description="""
Get active sessions with flexible time granularity.

**What is a "session"?**
A session represents a single app usage period, identified by a unique session_id.
Sessions automatically rotate every 2 hours and do not persist across app restarts.
This provides usage metrics without requiring user consent for tracking.

**Granularity Options:**
- `day` (default): Daily active sessions
- `week`: Weekly active sessions - ISO weeks, Mon-Sun
- `month`: Monthly active sessions
- `quarter`: Quarterly active sessions
- `year`: Yearly active sessions

**Period Labels:**
| Granularity | Format | Example |
|-------------|--------|---------|
| day | YYYY-MM-DD | 2025-11-27 |
| week | YYYY-Www | 2025-W48 |
| month | YYYY-MM | 2025-11 |
| quarter | YYYY-Qn | 2025-Q4 |
| year | YYYY | 2025 |
        """,
        manual_parameters=[
            openapi.Parameter(
                "X-App-Key",
                openapi.IN_HEADER,
                description="App Key for authentication",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "from",
                openapi.IN_QUERY,
                description="Start date in YYYY-MM-DD format",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "to",
                openapi.IN_QUERY,
                description="End date in YYYY-MM-DD format",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "tz",
                openapi.IN_QUERY,
                description=(
                    "IANA timezone name (e.g., 'America/New_York', 'Europe/London'). Dates are "
                    "interpreted in this timezone. Defaults to UTC."
                ),
                type=openapi.TYPE_STRING,
                required=False,
                default="UTC",
            ),
            openapi.Parameter(
                "granularity",
                openapi.IN_QUERY,
                description="Time period grouping: day (default), week, month, quarter, year",
                type=openapi.TYPE_STRING,
                enum=["day", "week", "month", "quarter", "year"],
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Active sessions data by period with session length metrics",
                examples={
                    "application/json": {
                        "app_name": "My App",
                        "granularity": "week",
                        "date_range": {"from": "2025-11-01", "to": "2025-11-27"},
                        "active_sessions": [
                            {
                                "period": "2025-W48",
                                "unique_sessions": 3456,
                                "total_events": 15234,
                                "avg_session_length_seconds": 245.3,
                                "sessions_with_duration": 2891,
                            },
                            {
                                "period": "2025-W47",
                                "unique_sessions": 3189,
                                "total_events": 14102,
                                "avg_session_length_seconds": 238.7,
                                "sessions_with_duration": 2654,
                            },
                            {
                                "period": "2025-W46",
                                "unique_sessions": 2987,
                                "total_events": 13456,
                                "avg_session_length_seconds": 251.2,
                                "sessions_with_duration": 2503,
                            },
                        ],
                        "summary": {
                            "total_sessions": 9632,
                            "sessions_with_duration": 8048,
                            "avg_session_length_seconds": 245.1,
                        },
                        "top_events_current_period": [
                            {"event_name": "app_open", "count": 5341},
                            {"event_name": "screen_view", "count": 4876},
                        ],
                    }
                },
            ),
            400: openapi.Response(
                description="Bad Request - invalid date format or granularity",
                examples={
                    "application/json": {
                        "error": (
                            "Invalid granularity. Must be one of: day, week, month, quarter, year"
                        )
                    }
                },
            ),
            401: "Unauthorized - missing or invalid app_key",
        },
    )
    def get(self, request):
        # Get the authenticated app
        app = request.user

        # Parse query parameters
        from_date_str = request.query_params.get("from")
        to_date_str = request.query_params.get("to")
        tz_name = request.query_params.get("tz", "UTC")
        granularity = request.query_params.get("granularity", "day").lower()

        # Validate granularity
        if granularity not in self.VALID_GRANULARITIES:
            return Response(
                {
                    "error": (
                        "Invalid granularity. Must be one of: "
                        f"{', '.join(self.VALID_GRANULARITIES)}"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # PERF-018: Cache DAU data for 2 minutes
        # DAU data updates with new events but is called every Overview tab load
        from django.conf import settings
        from django.core.cache import cache

        cache_key = get_cache_key_with_timezone(
            "dau", app.id, from_date_str, to_date_str, tz_name, granularity=granularity
        )
        cached_result = cache.get(cache_key)

        if cached_result is not None:
            return Response(cached_result)

        # Start with events for this app
        events = Event.objects.filter(app=app)

        # Parse and apply date filters (timezone-aware)
        from_date = None
        to_date = None

        try:
            from_date, to_date = parse_date_range(from_date_str, to_date_str, tz_name)
            if from_date:
                events = events.filter(timestamp__gte=from_date)
            if to_date:
                events = events.filter(timestamp__lte=to_date)
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Default range: the last 30 days, from the reader's midnight (analytics/date_utils.py)
        from_date, to_date = default_range(from_date, to_date, tz_name)
        events = events.filter(timestamp__gte=from_date, timestamp__lte=to_date)

        # Choose truncation function based on granularity
        trunc_functions = {
            "day": TruncDay,
            "week": TruncWeek,  # Django uses ISO weeks (Mon-Sun)
            "month": TruncMonth,
            "quarter": TruncQuarter,
            "year": TruncYear,
        }
        trunc_func = trunc_functions[granularity]
        # Periods are the reader's own days, weeks and months, as the range is: until 2026-10-25
        # they were cut in UTC, so a reader east of UTC got a first day of a few hours and each
        # day shifted by the offset (conversion/test_timezones.py)
        zone = _get_timezone_safe(tz_name)

        # Calculate active sessions per period
        # A "session" is a unique session_id (in-memory, max 2 hours)
        period_data = [
            {
                "period": row["period"],
                "unique_sessions": row["sessions"],
                "total_events": row["events"],
            }
            for row in sessions_per(
                slices_in(app, from_date, to_date)
                .filter(session_id__isnull=False)
                .exclude(session_id="")
                .annotate(period=trunc_func("quarter", tzinfo=zone)),
                ["period"],
                order='"period" DESC',
            )
        ]

        # Calculate average session length per period
        # Uses raw SQL for efficiency - calculates time between first and last event per session
        session_lengths = self._calculate_session_lengths(
            app.id, from_date, to_date, granularity, zone
        )

        # Format period labels based on granularity
        active_sessions = []
        total_sessions_with_length = 0
        total_duration_seconds = 0.0

        for item in period_data:
            period_dt = item["period"]
            if period_dt:
                period_label = self._format_period_label(period_dt, granularity)
                period_entry = {
                    "period": period_label,
                    "unique_sessions": item["unique_sessions"],
                    "unique_buckets": item["unique_sessions"],  # JS compatibility alias
                    "total_events": item["total_events"],
                }

                # Add session length data if available for this period
                if period_label in session_lengths:
                    length_data = session_lengths[period_label]
                    avg_duration = (
                        float(length_data["avg_duration"]) if length_data["avg_duration"] else None
                    )
                    period_entry["avg_session_length_seconds"] = (
                        round(avg_duration, 1) if avg_duration else None
                    )
                    period_entry["sessions_with_duration"] = length_data["session_count"]
                    total_sessions_with_length += length_data["session_count"]
                    if avg_duration:
                        total_duration_seconds += avg_duration * length_data["session_count"]
                else:
                    period_entry["avg_session_length_seconds"] = None
                    period_entry["sessions_with_duration"] = 0

                active_sessions.append(period_entry)

        # Get top events for the current/most recent period
        top_events = []
        if active_sessions:
            # Get the most recent period's data
            most_recent_period = period_data[0] if period_data else None
            if most_recent_period and most_recent_period["period"]:
                # Filter events for the most recent period
                period_start = most_recent_period["period"]
                period_end = self._get_period_end(period_start, granularity)

                top_events_qs = (
                    events.filter(timestamp__gte=period_start, timestamp__lt=period_end)
                    .values("event_name")
                    .annotate(count=Count("id"))
                    .order_by("-count")[:10]
                )
                top_events = list(top_events_qs)

        # Format response dates
        date_range = {
            "from": from_date.strftime("%Y-%m-%d") if from_date else None,
            "to": to_date.strftime("%Y-%m-%d") if to_date else None,
        }

        # Calculate overall summary stats
        total_unique_sessions = sum(item["unique_sessions"] for item in active_sessions)
        avg_session_length_overall = (
            round(total_duration_seconds / total_sessions_with_length, 1)
            if total_sessions_with_length > 0
            else None
        )

        response_data = {
            "app_name": app.name,
            "granularity": granularity,
            "date_range": date_range,
            "active_sessions": active_sessions,
            "summary": {
                "total_sessions": total_unique_sessions,
                "sessions_with_duration": total_sessions_with_length,
                "avg_session_length_seconds": avg_session_length_overall,
            },
            "top_events_current_period": top_events,
        }

        # Cache the result for 2 minutes
        cache_ttl = getattr(settings, "CACHE_TTL_SUMMARY", 120)
        cache.set(cache_key, response_data, timeout=cache_ttl)

        return Response(response_data, status=status.HTTP_200_OK)

    def _format_period_label(self, dt, granularity):
        """
        Format a datetime into the appropriate period label.

        Args:
            dt: datetime object (truncated to period start)
            granularity: one of 'day', 'week', 'month', 'quarter', 'year'

        Returns:
            Formatted string label for the period
        """
        if granularity == "day":
            return dt.strftime("%Y-%m-%d")
        elif granularity == "week":
            # ISO week format: YYYY-Www
            iso_cal = dt.isocalendar()
            return f"{iso_cal[0]}-W{iso_cal[1]:02d}"
        elif granularity == "month":
            return dt.strftime("%Y-%m")
        elif granularity == "quarter":
            quarter = (dt.month - 1) // 3 + 1
            return f"{dt.year}-Q{quarter}"
        elif granularity == "year":
            return str(dt.year)
        return dt.strftime("%Y-%m-%d")

    def _get_period_end(self, period_start, granularity):
        """
        Calculate the end datetime of a period for filtering.

        Args:
            period_start: datetime object at the start of the period
            granularity: one of 'day', 'week', 'month', 'quarter', 'year'

        Returns:
            datetime object at the start of the NEXT period
        """
        if granularity == "day":
            return period_start + timedelta(days=1)
        elif granularity == "week":
            return period_start + timedelta(weeks=1)
        elif granularity == "month":
            return period_start + relativedelta(months=1)
        elif granularity == "quarter":
            return period_start + relativedelta(months=3)
        elif granularity == "year":
            return period_start + relativedelta(years=1)
        return period_start + timedelta(days=1)

    def _calculate_session_lengths(self, app_id, from_date, to_date, granularity, zone):
        """
        Calculate average session length per period using raw SQL, from the session slices
        (analytics.SessionSlice): a session's first and last moments in the range, a row or two
        per session instead of every event.

        Session length = time between first and last event in a session.
        Only includes sessions with 2+ events (single-event sessions have no duration).
        Durations capped at 7200 seconds (2 hours) to handle session rotation edge cases.

        Args:
            app_id: UUID of the app
            from_date: Start datetime for the query
            to_date: End datetime for the query
            granularity: Time period grouping (day, week, month, quarter, year)
            zone: the reader's time zone, whose periods these are

        Returns:
            Dict mapping period labels to {avg_duration, session_count}
        """
        from django.db import connection

        # Determine truncation SQL based on granularity
        trunc_sql_map = {
            "day": "DATE_TRUNC('day', MIN(first_at) AT TIME ZONE %s)",
            "week": "DATE_TRUNC('week', MIN(first_at) AT TIME ZONE %s)",
            "month": "DATE_TRUNC('month', MIN(first_at) AT TIME ZONE %s)",
            "quarter": "DATE_TRUNC('quarter', MIN(first_at) AT TIME ZONE %s)",
            "year": "DATE_TRUNC('year', MIN(first_at) AT TIME ZONE %s)",
        }
        trunc_sql = trunc_sql_map.get(granularity, trunc_sql_map["day"])

        # Build date filter; the zone's placeholder comes first in the query, so its value too
        date_filter = ""
        params = [zone.key, str(app_id)]
        if from_date:
            date_filter += " AND quarter >= %s"
            params.append(from_date)
        if to_date:
            date_filter += " AND quarter <= %s"
            params.append(to_date)

        # SQL to calculate session lengths grouped by period
        # LEAST() caps duration at 7200 seconds (2 hours) for session rotation edge cases
        sql = f"""
        WITH session_durations AS (
            SELECT
                session_id COLLATE "C" AS session_id,
                {trunc_sql} as period,
                LEAST(
                    EXTRACT(EPOCH FROM (MAX(last_at) - MIN(first_at))),
                    7200
                ) as duration_seconds
            FROM analytics_sessionslice
            WHERE app_id = %s
                AND session_id IS NOT NULL
                AND session_id != ''
                {date_filter}
            GROUP BY 1
            HAVING SUM(events) > 1  -- Exclude single-event sessions
        )
        SELECT
            period,
            COUNT(*) as session_count,
            AVG(duration_seconds) as avg_duration
        FROM session_durations
        WHERE period IS NOT NULL
        GROUP BY period
        ORDER BY period DESC;
        """

        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        # Build result dict mapping period labels to data
        result = {}
        for row in rows:
            period_dt, session_count, avg_duration = row
            if period_dt:
                period_label = self._format_period_label(period_dt, granularity)
                result[period_label] = {
                    "session_count": session_count,
                    "avg_duration": round(avg_duration, 1) if avg_duration else None,
                }

        return result


class ConversionSummaryView(APIView):
    """
    GET /api/v1/analytics/conversions/ - Get Conversion Summary with flexible granularity

    Returns conversion counts and rates per period for specified conversion events.
    This is the core of Conversion Intelligence - understanding session conversion patterns.

    Query parameters:
        - conversion_events: REQUIRED - Comma-separated event names to count as conversions
        - from: Start date (YYYY-MM-DD)
        - to: End date (YYYY-MM-DD)
        - granularity: Time period grouping (day, week, month, quarter, year). Default: day

    Conversion rate is calculated as: sessions with conversions / total unique sessions per period
    """

    share_links = True  # a share link's dashboard reads it (teams/)
    authentication_classes = APP_OWNER
    permission_classes = [HasValidAppKey]

    # Valid granularity options (same as DAUView)
    VALID_GRANULARITIES = ("day", "week", "month", "quarter", "year")

    @swagger_auto_schema(
        operation_description="""
Get conversion summary with flexible time granularity.

**Required Parameter:**
The `conversion_events` parameter is **required**. Specify which events to count as conversions.

**Example:**
`?conversion_events=purchase,subscription_complete`

**What is a "conversion rate"?**
Conversion rate = sessions with conversions / total unique sessions per period.
A session is a unique app usage period (max 2 hours), identified by session_id.

**Granularity Options:**
- `day` (default): Daily conversion data
- `week`: Weekly conversions - ISO weeks, Mon-Sun
- `month`: Monthly conversions
- `quarter`: Quarterly conversions
- `year`: Yearly conversions

**Period Labels:**
| Granularity | Format | Example |
|-------------|--------|---------|
| day | YYYY-MM-DD | 2025-11-27 |
| week | YYYY-Www | 2025-W48 |
| month | YYYY-MM | 2025-11 |
| quarter | YYYY-Qn | 2025-Q4 |
| year | YYYY | 2025 |
        """,
        manual_parameters=[
            openapi.Parameter(
                "X-App-Key",
                openapi.IN_HEADER,
                description="App Key for authentication",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "conversion_events",
                openapi.IN_QUERY,
                description=(
                    "REQUIRED: Comma-separated event names to count as conversions (e.g., "
                    "purchase,subscription_complete)"
                ),
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "from",
                openapi.IN_QUERY,
                description="Start date in YYYY-MM-DD format",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "to",
                openapi.IN_QUERY,
                description="End date in YYYY-MM-DD format",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "tz",
                openapi.IN_QUERY,
                description=(
                    "IANA timezone name (e.g., 'America/New_York', 'Europe/London'). Dates are "
                    "interpreted in this timezone. Defaults to UTC."
                ),
                type=openapi.TYPE_STRING,
                required=False,
                default="UTC",
            ),
            openapi.Parameter(
                "granularity",
                openapi.IN_QUERY,
                description="Time period grouping: day (default), week, month, quarter, year",
                type=openapi.TYPE_STRING,
                enum=["day", "week", "month", "quarter", "year"],
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Conversion summary data by period",
                examples={
                    "application/json": {
                        "app_name": "My App",
                        "granularity": "month",
                        "conversion_events": ["purchase", "subscription_start"],
                        "date_range": {"from": "2025-09-01", "to": "2025-11-27"},
                        "summary": {"total_conversions": 1042, "avg_conversion_rate": 0.0312},
                        "conversions": [
                            {
                                "period": "2025-11",
                                "conversions": 342,
                                "active_sessions": 11793,
                                "conversion_rate": 0.029,
                            },
                            {
                                "period": "2025-10",
                                "conversions": 385,
                                "active_sessions": 12419,
                                "conversion_rate": 0.031,
                            },
                            {
                                "period": "2025-09",
                                "conversions": 315,
                                "active_sessions": 9265,
                                "conversion_rate": 0.034,
                            },
                        ],
                        "interpretation": (
                            "Conversion rate shows the percentage of sessions that include a "
                            "conversion event. Each session is analyzed independently."
                        ),
                    }
                },
            ),
            400: openapi.Response(
                description="Bad Request - missing conversion_events or invalid parameters",
                examples={
                    "application/json": {
                        "error": "conversion_events parameter required",
                        "detail": "Please specify which events to count as conversions.",
                        "your_event_types": [
                            "app_open",
                            "screen_view",
                            "button_click",
                            "checkout_start",
                            "payment_success",
                        ],
                        "example": "?conversion_events=payment_success,checkout_start",
                    }
                },
            ),
            401: "Unauthorized - missing or invalid app_key",
        },
    )
    def get(self, request):
        # Get the authenticated app
        app = request.user

        # Parse query parameters
        conversion_events_str = request.query_params.get("conversion_events")
        from_date_str = request.query_params.get("from")
        to_date_str = request.query_params.get("to")
        tz_name = request.query_params.get("tz", "UTC")
        granularity = request.query_params.get("granularity", "day").lower()

        # Validate conversion_events parameter (REQUIRED)
        if not conversion_events_str:
            # Get user's actual event types to help them
            event_types = list(
                Event.objects.filter(app=app)
                .values_list("event_name", flat=True)
                .distinct()
                .order_by("event_name")[:20]
            )
            return Response(
                {
                    "error": "conversion_events parameter required",
                    "detail": "Please specify which events to count as conversions.",
                    "your_event_types": event_types,
                    "example": "?conversion_events="
                    + (
                        ",".join(event_types[:2])
                        if len(event_types) >= 2
                        else "purchase,subscription"
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse conversion events (comma-separated, trimmed)
        conversion_events = [e.strip() for e in conversion_events_str.split(",") if e.strip()]

        if not conversion_events:
            return Response(
                {
                    "error": "conversion_events parameter is empty",
                    "detail": "Please specify at least one event name.",
                    "example": "?conversion_events=purchase,subscription",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate granularity
        if granularity not in self.VALID_GRANULARITIES:
            return Response(
                {
                    "error": (
                        "Invalid granularity. Must be one of: "
                        f"{', '.join(self.VALID_GRANULARITIES)}"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # PERF-006: Check cache before running expensive conversion analysis
        import hashlib

        from django.conf import settings
        from django.core.cache import cache

        cache_params = (
            f"{conversion_events_str}:{from_date_str}:{to_date_str}:{tz_name}:{granularity}"
        )
        cache_hash = hashlib.md5(cache_params.encode()).hexdigest()[:16]
        cache_key = f"conversion_summary:{app.id}:{cache_hash}"

        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return Response(cached_result, status=status.HTTP_200_OK)

        # Start with events for this app
        events = Event.objects.filter(app=app)

        # Parse and apply date filters (timezone-aware)
        from_date = None
        to_date = None

        try:
            from_date, to_date = parse_date_range(from_date_str, to_date_str, tz_name)
            if from_date:
                events = events.filter(timestamp__gte=from_date)
            if to_date:
                events = events.filter(timestamp__lte=to_date)
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Default range: the last 30 days, from the reader's midnight (analytics/date_utils.py)
        from_date, to_date = default_range(from_date, to_date, tz_name)
        events = events.filter(timestamp__gte=from_date, timestamp__lte=to_date)

        # Choose truncation function based on granularity
        trunc_functions = {
            "day": TruncDay,
            "week": TruncWeek,  # Django uses ISO weeks (Mon-Sun)
            "month": TruncMonth,
            "quarter": TruncQuarter,
            "year": TruncYear,
        }
        trunc_func = trunc_functions[granularity]
        zone = _get_timezone_safe(tz_name)  # the reader's own periods, as in DAUView

        # Calculate active sessions per period (same logic as DAUView)
        active_sessions_data = sessions_per(
            slices_in(app, from_date, to_date)
            .filter(session_id__isnull=False)
            .exclude(session_id="")
            .annotate(period=trunc_func("quarter", tzinfo=zone)),
            ["period"],
        )

        # Convert to dict for easy lookup
        sessions_by_period = {item["period"]: item["sessions"] for item in active_sessions_data}

        # Sessions with a conversion event per period: a rate of sessions over sessions, which
        # never passes 100% (until 2026-10-24 it counted the events, so a session that bought
        # twice counted twice)
        conversion_data = (
            events.filter(event_name__in=conversion_events, session_id__isnull=False)
            .exclude(session_id="")
            .annotate(period=trunc_func("timestamp", tzinfo=zone))
            .values("period")
            .annotate(conversions=Count("session_id", distinct=True))
            .order_by("-period")
        )

        # Format response data with conversion rates
        conversions_list = []
        total_conversions = 0

        for item in conversion_data:
            period_dt = item["period"]
            if period_dt:
                period_label = self._format_period_label(period_dt, granularity)
                active_sessions = sessions_by_period.get(period_dt, 0)
                conversion_count = item["conversions"]

                # Calculate conversion rate (avoid division by zero)
                conversion_rate = (
                    round(conversion_count / active_sessions, 4) if active_sessions > 0 else 0.0
                )

                conversions_list.append(
                    {
                        "period": period_label,
                        "conversions": conversion_count,
                        "active_sessions": active_sessions,
                        "conversion_rate": conversion_rate,
                    }
                )

                total_conversions += conversion_count

        # The rate over the whole range: every period's sessions, with a conversion or not
        total_sessions_for_avg = sum(sessions_by_period.values())
        avg_conversion_rate = (
            round(total_conversions / total_sessions_for_avg, 4)
            if total_sessions_for_avg > 0
            else 0.0
        )

        # Format response dates
        date_range = {
            "from": from_date.strftime("%Y-%m-%d") if from_date else None,
            "to": to_date.strftime("%Y-%m-%d") if to_date else None,
        }

        response_data = {
            "app_name": app.name,
            "granularity": granularity,
            "conversion_events": conversion_events,
            "date_range": date_range,
            "summary": {
                "total_conversions": total_conversions,
                "avg_conversion_rate": avg_conversion_rate,
            },
            "conversions": conversions_list,
            "interpretation": (
                "Conversion rate shows the percentage of sessions that include a conversion event. "
                "Each session is analyzed independently."
            ),
        }

        # Cache the result for 2 minutes
        cache_ttl = getattr(settings, "CACHE_TTL_CONVERSION", 120)
        cache.set(cache_key, response_data, timeout=cache_ttl)

        return Response(response_data, status=status.HTTP_200_OK)

    def _format_period_label(self, dt, granularity):
        """
        Format a datetime into the appropriate period label.

        Args:
            dt: datetime object (truncated to period start)
            granularity: one of 'day', 'week', 'month', 'quarter', 'year'

        Returns:
            Formatted string label for the period
        """
        if granularity == "day":
            return dt.strftime("%Y-%m-%d")
        elif granularity == "week":
            # ISO week format: YYYY-Www
            iso_cal = dt.isocalendar()
            return f"{iso_cal[0]}-W{iso_cal[1]:02d}"
        elif granularity == "month":
            return dt.strftime("%Y-%m")
        elif granularity == "quarter":
            quarter = (dt.month - 1) // 3 + 1
            return f"{dt.year}-Q{quarter}"
        elif granularity == "year":
            return str(dt.year)
        return dt.strftime("%Y-%m-%d")


class TimeToConversionView(APIView):
    """
    API endpoint for analyzing time-to-conversion metrics.

    This endpoint calculates how long it takes sessions to complete conversion events
    after their first interaction with the app. It provides statistical summaries
    (median, mean, percentiles) and time distribution buckets.

    This is a session-based analysis - each session is analyzed independently.

    Query Parameters:
        app_id (required): The application slug to filter events
        conversion_events (required): Comma-separated list of event names to
            consider as conversion events (e.g., "purchase,subscription_start")
        start_date (optional): Filter events from this date (YYYY-MM-DD)
        end_date (optional): Filter events to this date (YYYY-MM-DD)

    Returns:
        200 OK: Time-to-conversion analysis with statistics, distributions,
            and data quality metrics
        400 Bad Request: If fewer than 10 sessions have conversions
            (insufficient data for meaningful analysis)
        404 Not Found: If app_id doesn't exist or user doesn't have access

    Response Structure:
        {
            "app": {"id": int, "name": str, "slug": str},
            "filters": {"start_date": str|null, "end_date": str|null, "conversion_events": [str]},
            "data_quality": {
                "sessions_with_conversions": int,
                "coverage_percent": float,
                "warning": str|null
            },
            "time_to_conversion": {
                "median_minutes": float,
                "mean_minutes": float,
                "p25_minutes": float,
                "p75_minutes": float,
                "p90_minutes": float,
                "min_minutes": float,
                "max_minutes": float
            },
            "time_distribution": {
                "under_5_min": {"count": int, "percent": float},
                "5_to_15_min": {"count": int, "percent": float},
                "15_to_60_min": {"count": int, "percent": float},
                "1_to_2_hours": {"count": int, "percent": float}
            }
        }
    """

    share_links = True  # a share link's dashboard reads it (teams/)
    authentication_classes = APP_OWNER
    permission_classes = [HasValidAppKey]

    # Show data even with 1 session - frontend shows small sample warning
    MINIMUM_USERS_THRESHOLD = 1

    @swagger_auto_schema(
        operation_summary="Get time-to-conversion analysis",
        operation_description="""
Analyze how long it takes sessions to complete conversion events after their first
interaction with the app. This is a session-based analysis.

**Required Parameters:**
- `conversion_events`: Comma-separated conversion event names

**Data Quality:**
- Minimum 10 sessions with conversions required for meaningful analysis
- Data quality metrics included in response

**Statistics Provided:**
- Median, mean, and percentiles (p25, p75, p90) for time-to-conversion
- Time buckets: <5min, 5-15min, 15-60min, 1-2h (session-bounded)
        """,
        manual_parameters=[
            openapi.Parameter(
                "conversion_events",
                openapi.IN_QUERY,
                description="Comma-separated list of conversion event names (required)",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                description="Start date filter (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                description="End date filter (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
            ),
            openapi.Parameter(
                "tz",
                openapi.IN_QUERY,
                description=(
                    "IANA timezone name (e.g., 'America/New_York', 'Europe/London'). Dates are "
                    "interpreted in this timezone. Defaults to UTC."
                ),
                type=openapi.TYPE_STRING,
                required=False,
                default="UTC",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Time-to-conversion analysis",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "app": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "filters": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "data_quality": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "time_to_conversion": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "time_distribution": openapi.Schema(type=openapi.TYPE_OBJECT),
                    },
                ),
            ),
            400: openapi.Response(description="Missing required parameters or insufficient data"),
            401: openapi.Response(description="Unauthorized - missing or invalid app_key"),
        },
        tags=["Analytics"],
    )
    def get(self, request):
        """
        Get time-to-conversion analysis for an application.
        """
        # Get the authenticated app
        app = request.user

        # Validate required parameters
        conversion_events_param = request.query_params.get("conversion_events")

        if not conversion_events_param:
            # Get user's actual event types to help them
            event_types = list(
                Event.objects.filter(app=app)
                .values_list("event_name", flat=True)
                .distinct()
                .order_by("event_name")[:20]
            )
            return Response(
                {
                    "error": "conversion_events parameter is required",
                    "detail": "Please specify which events to count as conversions.",
                    "your_event_types": event_types,
                    "example": "?conversion_events="
                    + (
                        ",".join(event_types[:2])
                        if len(event_types) >= 2
                        else "purchase,subscription"
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse conversion events
        conversion_events = [e.strip() for e in conversion_events_param.split(",") if e.strip()]

        if not conversion_events:
            return Response(
                {
                    "error": "conversion_events parameter is empty",
                    "detail": "Please specify at least one event name.",
                    "example": "?conversion_events=purchase,subscription",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse date filters
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        tz_name = request.query_params.get("tz", "UTC")

        # PERF-009: Check cache before running expensive analysis
        import hashlib

        from django.conf import settings
        from django.core.cache import cache

        cache_params = f"{','.join(sorted(conversion_events))}:{start_date}:{end_date}:{tz_name}"
        cache_hash = hashlib.md5(cache_params.encode()).hexdigest()[:16]
        cache_key = f"time_to_conversion:{app.id}:{cache_hash}"

        cached_result = cache.get(cache_key)
        if cached_result is not None:
            # Check if this is a cached error response
            if "_error" in cached_result:
                return Response(cached_result["_error"], status=status.HTTP_400_BAD_REQUEST)
            return Response(cached_result, status=status.HTTP_200_OK)

        # Parse dates with timezone awareness
        try:
            start_datetime, end_datetime = parse_date_range(start_date, end_date, tz_name)
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Build base queryset
        events_qs = Event.objects.filter(app=app)

        if start_datetime:
            events_qs = events_qs.filter(timestamp__gte=start_datetime)
        if end_datetime:
            events_qs = events_qs.filter(timestamp__lte=end_datetime)

        # Get total sessions count for coverage calculation, from the range's session slices
        # (analytics/base_events.py)
        all_sessions_count = session_count(slices_in(app, start_datetime, end_datetime))

        # Get conversion analysis data (session-based)
        analysis_result = self._calculate_time_to_conversion(
            app, events_qs, conversion_events, all_sessions_count
        )

        if "error" in analysis_result:
            # PERF-009: Cache error responses too (shorter TTL - 1 min)
            cache.set(cache_key, {"_error": analysis_result}, timeout=60)
            return Response(analysis_result, status=status.HTTP_400_BAD_REQUEST)

        response_data = {
            "app": {"id": app.id, "name": app.name, "slug": app.slug},
            "filters": {
                "start_date": start_date,
                "end_date": end_date,
                "conversion_events": conversion_events,
            },
            **analysis_result,
        }

        # PERF-009: Cache the result for 3 minutes
        cache.set(cache_key, response_data, timeout=settings.CACHE_TTL_CONVERSION)

        return Response(response_data, status=status.HTTP_200_OK)

    def _calculate_time_to_conversion(self, app, events_qs, conversion_events, all_sessions_count):
        """
        Calculate time-to-conversion statistics using session-based analysis.

        Session-Based Approach:
        - Analyzes time from first event in a session to conversion event
        - Each session is independent (no cross-session tracking)
        - Only sessions that contain a conversion are analyzed
        - Time is bounded to session duration (max ~2 hours)

        Returns analysis results or error dict if insufficient data.
        """
        from django.db import connection

        # Get the SQL and params from the Django queryset (for base filtering)
        base_sql, base_params = base_events(events_qs)

        # Build conversion events placeholder for SQL
        conversion_placeholders = ", ".join(["%s"] * len(conversion_events))

        # Session-based time to conversion, counted in the database in one row: each converting
        # session's minutes from its first event to its first conversion event (the first events
        # read only for converting sessions, on the (app, session_id, timestamp) index), held to
        # a session's two hours, then their percentiles (percentile_cont interpolates as the
        # Python reading did), mean, extremes and buckets
        analysis_sql = f"""
        WITH base_events AS NOT MATERIALIZED ({base_sql}),
        first_conversion AS (
            SELECT session_id, MIN(timestamp) AS at
            FROM base_events
            WHERE session_id IS NOT NULL AND session_id != ''
              AND event_name IN ({conversion_placeholders})
            GROUP BY session_id
        ),
        first_event AS (
            SELECT e.session_id, MIN(e.timestamp) AS at
            FROM base_events e
            JOIN first_conversion c ON c.session_id = e.session_id
            GROUP BY e.session_id
        ),
        minutes AS (
            SELECT (EXTRACT(EPOCH FROM (c.at - f.at)) / 60.0)::float8 AS m
            FROM first_event f
            JOIN first_conversion c ON c.session_id = f.session_id
        )
        SELECT COUNT(m),
            percentile_cont(ARRAY[0.25, 0.5, 0.75, 0.9]) WITHIN GROUP (ORDER BY m),
            AVG(m), MIN(m), MAX(m),
            COUNT(*) FILTER (WHERE m < 5),
            COUNT(*) FILTER (WHERE m >= 5 AND m < 15),
            COUNT(*) FILTER (WHERE m >= 15 AND m < 60),
            COUNT(*) FILTER (WHERE m >= 60)
        FROM minutes
        WHERE m >= 0 AND m <= 120  -- Session bounded: max 2 hours
        """

        params = list(base_params) + list(conversion_events)
        with connection.cursor() as cursor:
            cursor.execute(analysis_sql, params)
            row = cursor.fetchone()
        sessions_with_conversions, quartiles, mean, least, most, *buckets = row

        # Handle zero conversions case
        if sessions_with_conversions == 0:
            return {
                "data_quality": {
                    "sessions_with_conversions": 0,
                    "total_sessions": all_sessions_count,
                    "coverage_percent": 0,
                    "warning": None,
                    "small_sample_warning": None,
                },
                "time_to_conversion": self._calculate_percentile_stats([]),
                "time_distribution": self._calculate_time_distribution([]),
            }

        # Calculate coverage percentage
        coverage_percent = (
            (sessions_with_conversions / all_sessions_count * 100) if all_sessions_count > 0 else 0
        )

        # Generate warnings
        warning = None
        small_sample_warning = None

        if coverage_percent < 5:
            warning = f"Low conversion rate: only {coverage_percent:.1f}% of sessions converted"

        # Add small sample warning if < 10 sessions (for UI to show advisory)
        if sessions_with_conversions < 10:
            small_sample_warning = (
                f"Small sample size: {sessions_with_conversions} converting "
                f"session{'s' if sessions_with_conversions != 1 else ''}. Results may vary with "
                "more data."
            )

        # Statistics, from the database's one row
        p25, median, p75, p90 = quartiles
        time_stats = {
            "median_minutes": round(median, 2),
            "mean_minutes": round(mean, 2),
            "p25_minutes": round(p25, 2),
            "p75_minutes": round(p75, 2),
            "p90_minutes": round(p90, 2),
            "min_minutes": round(least, 2),
            "max_minutes": round(most, 2),
        }
        time_distribution = {
            key: {"count": count, "percent": round(count / sessions_with_conversions * 100, 2)}
            for key, count in zip(
                ("under_5_min", "5_to_15_min", "15_to_60_min", "1_to_2_hours"), buckets, strict=True
            )
        }

        return {
            "data_quality": {
                "sessions_with_conversions": sessions_with_conversions,
                "total_sessions": all_sessions_count,
                "coverage_percent": round(coverage_percent, 2),
                "warning": warning,
                "small_sample_warning": small_sample_warning,
            },
            "time_to_conversion": time_stats,
            "time_distribution": time_distribution,
        }

    def _calculate_percentile_stats(self, values):
        """
        Calculate percentile statistics for a list of values.

        Returns dict with median, mean, p25, p75, p90, min, max.
        """
        if not values:
            return {
                "median_minutes": 0,
                "mean_minutes": 0,
                "p25_minutes": 0,
                "p75_minutes": 0,
                "p90_minutes": 0,
                "min_minutes": 0,
                "max_minutes": 0,
            }

        sorted_values = sorted(values)
        n = len(sorted_values)

        def percentile(p):
            """Calculate percentile using linear interpolation."""
            if n == 1:
                return sorted_values[0]
            k = (n - 1) * p / 100.0
            f = int(k)
            c = f + 1 if f + 1 < n else f
            if f == c:
                return sorted_values[f]
            return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)

        return {
            "median_minutes": round(percentile(50), 2),
            "mean_minutes": round(sum(values) / len(values), 2),
            "p25_minutes": round(percentile(25), 2),
            "p75_minutes": round(percentile(75), 2),
            "p90_minutes": round(percentile(90), 2),
            "min_minutes": round(min(values), 2),
            "max_minutes": round(max(values), 2),
        }

    def _calculate_time_distribution(self, conversion_times):
        """
        Calculate distribution of conversion times across time buckets.

        Session-bounded buckets (max 2 hours):
        - under_5_min: < 5 minutes
        - 5_to_15_min: 5-15 minutes
        - 15_to_60_min: 15-60 minutes
        - 1_to_2_hours: 60-120 minutes
        """
        total = len(conversion_times)

        if total == 0:
            return {
                "under_5_min": {"count": 0, "percent": 0},
                "5_to_15_min": {"count": 0, "percent": 0},
                "15_to_60_min": {"count": 0, "percent": 0},
                "1_to_2_hours": {"count": 0, "percent": 0},
            }

        buckets = {"under_5_min": 0, "5_to_15_min": 0, "15_to_60_min": 0, "1_to_2_hours": 0}

        for time_minutes in conversion_times:
            if time_minutes < 5:
                buckets["under_5_min"] += 1
            elif time_minutes < 15:
                buckets["5_to_15_min"] += 1
            elif time_minutes < 60:
                buckets["15_to_60_min"] += 1
            else:
                buckets["1_to_2_hours"] += 1

        return {
            key: {"count": count, "percent": round(count / total * 100, 2)}
            for key, count in buckets.items()
        }


class StepTimingView(APIView):
    """
    API endpoint for analyzing funnel step timing within sessions.

    This endpoint analyzes the time between consecutive steps in a user-defined
    funnel. This is a **session-based** analysis.

    Design Decision: Session-Based Analysis
    Step timing is calculated for events within the same session_id. This approach:
    - Works for 100% of sessions (no exclusions)
    - Matches typical use case (in-session funnel analysis)
    - Privacy-compliant (no cross-session tracking)
    - No minimum session threshold required
    - Simple, intuitive, industry-standard

    Query Parameters:
        steps (required): Comma-separated list of event names defining the funnel
            (e.g., "onboarding_start,onboarding_complete,purchase")
        start_date (optional): Filter events from this date (YYYY-MM-DD)
        end_date (optional): Filter events to this date (YYYY-MM-DD)

    Returns:
        200 OK: Funnel step timing analysis with per-transition statistics
            and overall funnel summary
        400 Bad Request: If steps parameter is missing or has fewer than 2 steps

    Response Structure:
        {
            "app": {"id": int, "name": str, "slug": str},
            "steps": [str, ...],
            "filters": {"start_date": str|null, "end_date": str|null},
            "transitions": [
                {
                    "from": str,
                    "to": str,
                    "sessions_analyzed": int,
                    "median_seconds": float,
                    "mean_seconds": float,
                    "p25_seconds": float,
                    "p75_seconds": float
                },
                ...
            ],
            "funnel_summary": {
                "sessions_with_first_step": int,
                "sessions_with_all_steps": int,
                "completion_rate": float,
                "median_total_seconds": float,
                "mean_total_seconds": float
            }
        }
    """

    share_links = True  # a share link's dashboard reads it (teams/)
    authentication_classes = APP_OWNER
    permission_classes = [HasValidAppKey]

    @swagger_auto_schema(
        operation_summary="Analyze funnel step timing",
        operation_description="""
Analyze the time between consecutive steps in a user-defined funnel.

**Session-Based Analysis:**
This endpoint analyzes events within the **same session_id**. This means:
- Works for 100% of your sessions (including anonymous visitors)
- No data quality warnings or exclusions
- Perfect for in-session funnel analysis

**Example Use Cases:**
- How long does onboarding take? (`steps=onboarding_start,onboarding_complete`)
- Where do sessions slow down in signup?
  (`steps=signup_start,email_entered,password_set,signup_complete`)
- How long between pricing view and purchase? (`steps=pricing_view,purchase`)

**Statistics Provided:**
- Time between each consecutive step pair (median, mean, p25, p75 in seconds)
- Number of sessions analyzed per transition
- Overall funnel completion rate
- Total funnel duration
        """,
        manual_parameters=[
            GROUP_EVENTS,
            openapi.Parameter(
                "steps",
                openapi.IN_QUERY,
                description="Comma-separated list of funnel step event names (required, minimum 2)",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "country",
                openapi.IN_QUERY,
                description="Only these countries, comma-separated codes (e.g., 'US,SE')",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "platform",
                openapi.IN_QUERY,
                description="Only these platforms, comma-separated (ios, android, web, other)",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                description="Start date filter (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                description="End date filter (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
            ),
            openapi.Parameter(
                "tz",
                openapi.IN_QUERY,
                description=(
                    "IANA timezone name (e.g., 'America/New_York', 'Europe/London'). Dates are "
                    "interpreted in this timezone. Defaults to UTC."
                ),
                type=openapi.TYPE_STRING,
                required=False,
                default="UTC",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Funnel step timing analysis",
                examples={
                    "application/json": {
                        "app": {"id": 1, "name": "My App", "slug": "my-app"},
                        "steps": ["onboarding_start", "onboarding_complete", "purchase"],
                        "filters": {"start_date": None, "end_date": None},
                        "transitions": [
                            {
                                "from": "onboarding_start",
                                "to": "onboarding_complete",
                                "sessions_analyzed": 1234,
                                "median_seconds": 45,
                                "mean_seconds": 52,
                                "p25_seconds": 30,
                                "p75_seconds": 65,
                            },
                            {
                                "from": "onboarding_complete",
                                "to": "purchase",
                                "sessions_analyzed": 234,
                                "median_seconds": 120,
                                "mean_seconds": 145,
                                "p25_seconds": 60,
                                "p75_seconds": 180,
                            },
                        ],
                        "funnel_summary": {
                            "sessions_with_first_step": 1234,
                            "sessions_with_all_steps": 234,
                            "completion_rate": 0.190,
                            "median_total_seconds": 165,
                            "mean_total_seconds": 197,
                        },
                    }
                },
            ),
            400: openapi.Response(description="Missing or invalid steps parameter"),
            401: openapi.Response(description="Unauthorized - missing or invalid app_key"),
        },
        tags=["Analytics"],
    )
    def get(self, request):
        """
        Get funnel step timing analysis for an application.
        """
        # Get the authenticated app
        app = request.user

        # Validate required parameters
        steps_param = request.query_params.get("steps")

        if not steps_param:
            # Get user's actual event types to help them
            event_types = list(
                Event.objects.filter(app=app)
                .values_list("event_name", flat=True)
                .distinct()
                .order_by("event_name")[:20]
            )
            return Response(
                {
                    "error": "steps parameter is required",
                    "detail": "Please specify the funnel steps as comma-separated event names.",
                    "your_event_types": event_types,
                    "example": "?steps="
                    + (",".join(event_types[:3]) if len(event_types) >= 3 else "step1,step2,step3"),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse steps
        steps = [s.strip() for s in steps_param.split(",") if s.strip()]

        if len(steps) < 2:
            return Response(
                {
                    "error": "steps parameter requires at least 2 events",
                    "detail": "A funnel needs at least a start and end step.",
                    "example": "?steps=onboarding_start,onboarding_complete",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(steps) > 10:
            return Response(
                {
                    "error": "Maximum 10 steps allowed for step timing analysis",
                    "detail": "Please reduce the number of funnel steps to 10 or fewer.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse date filters
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        tz_name = request.query_params.get("tz", "UTC")

        # Parse dates with timezone awareness
        try:
            start_datetime, end_datetime = parse_date_range(start_date, end_date, tz_name)
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Cached by its question, as every conversion view is
        import hashlib

        from django.conf import settings
        from django.core.cache import cache

        # The funnel's own filters, read as it reads them (analytics/views.py), so its timings
        # are about the same sessions
        countries = sorted(
            {c.strip() for c in (request.query_params.get("country") or "").split(",") if c.strip()}
        )
        asked = [
            p.strip() for p in (request.query_params.get("platform") or "").split(",") if p.strip()
        ]
        platforms = sorted(set(asked) | {platform_name(p) for p in asked})

        grouping = event_groups.from_request(request, app)
        cache_params = (
            f"{','.join(steps)}:{start_date}:{end_date}:{tz_name}:{grouping.key()}:"
            f"{','.join(countries)}:{','.join(platforms)}"
        )
        cache_hash = hashlib.md5(cache_params.encode()).hexdigest()[:16]
        cache_key = f"step_timing:{app.id}:{cache_hash}"
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return Response(cached_result, status=status.HTTP_200_OK)

        # Build base queryset
        events_qs = Event.objects.filter(app=app)
        if countries:
            events_qs = events_qs.filter(country__in=countries)
        if platforms:
            events_qs = events_qs.filter(platform__in=platforms)

        if start_datetime:
            events_qs = events_qs.filter(timestamp__gte=start_datetime)
        if end_datetime:
            events_qs = events_qs.filter(timestamp__lte=end_datetime)

        # Calculate step timing analysis; a step may be a group's name (`group_events=true`)
        analysis_result = self._calculate_step_timing(events_qs, steps, grouping)

        response_data = {
            "app": {"id": app.id, "name": app.name, "slug": app.slug},
            "steps": steps,
            "filters": {
                "start_date": start_date,
                "end_date": end_date,
                "country": countries,
                "platform": platforms,
            },
            **analysis_result,
        }
        cache.set(cache_key, response_data, timeout=settings.CACHE_TTL_CONVERSION)
        return Response(response_data, status=status.HTTP_200_OK)

    def _calculate_step_timing(self, events_qs, steps, grouping=event_groups.NONE):
        """
        Timing between consecutive funnel steps within sessions, in one SQL aggregate.

        Each session's first time at each step is read in one pass over the steps' events
        (the (app, event_name, timestamp) index), and every count, percentile and mean is taken
        in the database, so one row comes back however many sessions there are. A step whose
        names all belong to a later step stands for nothing, as a name counts for the last step
        that holds it; conversion/test_step_timing.py holds this to the Python reading it
        replaced.

        Returns:
            dict with 'transitions' and 'funnel_summary'
        """
        from django.db import connection

        # Every event a step stands for: itself, or a group's events; a name counts for the
        # last step that holds it
        step_index = {}
        for i, step in enumerate(steps):
            for name in grouping.expand([step]):
                step_index[name] = i
        names = [[n for n, j in step_index.items() if j == i] for i in range(len(steps))]

        base_sql, base_params = base_events(events_qs)
        firsts, first_params = [], []
        for i, step_names in enumerate(names):
            if step_names:
                firsts.append(
                    f"MIN(timestamp) FILTER (WHERE event_name IN "
                    f"({', '.join(['%s'] * len(step_names))})) AS t{i}"
                )
                first_params += step_names
            else:
                firsts.append(f"NULL::timestamptz AS t{i}")
        last = len(steps) - 1
        gaps = [
            f"CASE WHEN t{i + 1} >= t{i} THEN EXTRACT(EPOCH FROM t{i + 1} - t{i})::float8 END "
            f"AS d{i}"
            for i in range(last)
        ]
        in_order = " AND ".join(f"t{i + 1} >= t{i}" for i in range(last))
        stats = [
            f"COUNT(d{i}), percentile_cont(ARRAY[0.25, 0.5, 0.75]) WITHIN GROUP "
            f"(ORDER BY d{i}), AVG(d{i})"
            for i in range(last)
        ]
        sql = f"""
        WITH base_events AS ({base_sql}),
        firsts AS (
            SELECT {", ".join(firsts)}
            FROM base_events
            WHERE event_name IN ({", ".join(["%s"] * len(step_index))})
            GROUP BY session_id
        ),
        timed AS (
            SELECT t0, {", ".join(gaps)},
                CASE WHEN {in_order} THEN EXTRACT(EPOCH FROM t{last} - t0)::float8 END AS total
            FROM firsts
        )
        SELECT COUNT(t0), COUNT(total),
            percentile_cont(0.5) WITHIN GROUP (ORDER BY total), AVG(total),
            {", ".join(stats)}
        FROM timed
        """
        params = [*base_params, *first_params, *step_index]
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()

        def seconds(value):
            return round(value, 2) if value is not None else 0

        transitions = []
        for i in range(last):
            analyzed, quartiles, mean = row[4 + 3 * i : 7 + 3 * i]
            p25, median, p75 = quartiles or (None, None, None)
            transitions.append(
                {
                    "from": steps[i],
                    "to": steps[i + 1],
                    "sessions_analyzed": analyzed,
                    "median_seconds": seconds(median),
                    "mean_seconds": seconds(mean),
                    "p25_seconds": seconds(p25),
                    "p75_seconds": seconds(p75),
                }
            )

        with_first, with_all, median_total, mean_total = row[:4]
        completion_rate = with_all / with_first if with_first > 0 else 0
        funnel_summary = {
            "sessions_with_first_step": with_first,
            "sessions_with_all_steps": with_all,
            "completion_rate": round(completion_rate, 3),
            "median_total_seconds": seconds(median_total),
            "mean_total_seconds": seconds(mean_total),
        }
        return {"transitions": transitions, "funnel_summary": funnel_summary}


class ConversionPathsView(APIView):
    """
    GET /api/v1/analytics/conversion-paths/ - Auto-discover conversion paths

    Automatically discovers the most common behavior sequences that lead to
    conversion within sessions. No manual funnel configuration required -
    the system finds patterns by analyzing session journeys.

    This is a **session-based** analysis. Each session is analyzed independently
    to find the event sequences that lead to conversion within that session.

    Query Parameters:
        conversion_events (required): Comma-separated list of event names to
            count as conversion events (e.g., "purchase,subscription_start")
        limit (optional): Maximum number of paths to return (default: 5, max: 20)
        min_sessions (optional): Minimum number of sessions for a path to be included
            (default: 3, helps filter noise)
        max_path_length (optional): Maximum events in a path (default: 10)
        start_date (optional): Filter events from this date (YYYY-MM-DD)
        end_date (optional): Filter events to this date (YYYY-MM-DD)

    Returns:
        200 OK: Top conversion paths with statistics
        400 Bad Request: If conversion_events is missing or invalid parameters

    Algorithm:
        1. Find all sessions with at least one conversion event
        2. For each converting session, extract the event sequence before conversion
        3. Normalize paths (deduplicate consecutive events, limit length)
        4. Group identical paths and count frequency
        5. Rank by number of sessions, calculate timing statistics
    """

    share_links = True  # a share link's dashboard reads it (teams/)
    authentication_classes = APP_OWNER
    permission_classes = [HasValidAppKey]

    # Minimum sessions required for analysis
    MINIMUM_SESSIONS_THRESHOLD = 3

    @swagger_auto_schema(
        operation_summary="Discover top conversion paths",
        operation_description="""
Automatically discover the most common behavior sequences that lead to conversion within sessions.

**Required Parameter:**
- `conversion_events`: Comma-separated event names (e.g., "purchase,subscription_start")

**What This Endpoint Does:**
1. Finds all sessions that include a conversion event
2. Extracts the event sequence leading to conversion within each session
3. Groups common patterns and ranks by frequency
4. Returns top N paths with timing statistics

**Session-Based Analysis:**
- Each session is analyzed independently (no cross-session tracking)
- Paths show what happens within a single app usage period
- Maximum session duration is ~2 hours

**Use Cases:**
- Discover which in-session journeys lead to purchase
- Find the most effective onboarding flows
- Identify hidden conversion patterns within sessions
        """,
        manual_parameters=[
            GROUP_EVENTS,
            openapi.Parameter(
                "conversion_events",
                openapi.IN_QUERY,
                description="REQUIRED: Comma-separated event names to count as conversions",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="Maximum number of paths to return (default: 5, max: 20)",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "min_sessions",
                openapi.IN_QUERY,
                description="Minimum sessions for a path to be included (default: 3)",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "max_path_length",
                openapi.IN_QUERY,
                description="Maximum events in a path before conversion (default: 10)",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                description="Start date filter (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                description="End date filter (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
            ),
            openapi.Parameter(
                "tz",
                openapi.IN_QUERY,
                description=(
                    "IANA timezone name (e.g., 'America/New_York', 'Europe/London'). Dates are "
                    "interpreted in this timezone. Defaults to UTC."
                ),
                type=openapi.TYPE_STRING,
                required=False,
                default="UTC",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Top conversion paths with statistics",
                examples={
                    "application/json": {
                        "app": {"id": 1, "name": "My App", "slug": "my-app"},
                        "filters": {
                            "conversion_events": ["purchase"],
                            "start_date": None,
                            "end_date": None,
                            "limit": 5,
                            "min_sessions": 3,
                            "max_path_length": 10,
                        },
                        "data_quality": {
                            "total_converting_sessions": 234,
                            "paths_analyzed": 187,
                            "unique_paths_found": 42,
                        },
                        "top_conversion_paths": [
                            {
                                "rank": 1,
                                "path": ["app_open", "feature_demo", "pricing_view", "purchase"],
                                "sessions": 89,
                                "conversion_rate": 0.42,
                                "avg_duration_minutes": 15.5,
                                "step_timings": [
                                    {"from": "app_open", "to": "feature_demo", "avg_minutes": 2.3},
                                    {
                                        "from": "feature_demo",
                                        "to": "pricing_view",
                                        "avg_minutes": 8.1,
                                    },
                                    {"from": "pricing_view", "to": "purchase", "avg_minutes": 5.1},
                                ],
                            }
                        ],
                        "interpretation": (
                            "These paths show what sessions do before they convert. Each session "
                            "is analyzed independently."
                        ),
                    }
                },
            ),
            400: openapi.Response(description="Missing or invalid parameters"),
            401: openapi.Response(description="Unauthorized - missing or invalid app_key"),
        },
        tags=["Analytics"],
    )
    def get(self, request):
        """
        Get auto-discovered conversion paths for an application.
        """
        # Get the authenticated app
        app = request.user

        # Validate required parameters
        conversion_events_param = request.query_params.get("conversion_events")

        if not conversion_events_param:
            # Get user's actual event types to help them
            event_types = list(
                Event.objects.filter(app=app)
                .values_list("event_name", flat=True)
                .distinct()
                .order_by("event_name")[:20]
            )
            return Response(
                {
                    "error": "conversion_events parameter is required",
                    "detail": "Please specify which events to count as conversions.",
                    "your_event_types": event_types,
                    "example": "?conversion_events="
                    + (
                        ",".join(event_types[:2])
                        if len(event_types) >= 2
                        else "purchase,subscription"
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse conversion events
        conversion_events = [e.strip() for e in conversion_events_param.split(",") if e.strip()]

        if not conversion_events:
            return Response(
                {
                    "error": "conversion_events parameter is empty",
                    "detail": "Please specify at least one event name.",
                    "example": "?conversion_events=purchase,subscription",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse optional parameters
        try:
            limit = int(request.query_params.get("limit", 5))
            limit = min(max(1, limit), 20)  # Clamp between 1 and 20
        except (ValueError, TypeError):
            return Response(
                {
                    "error": "Invalid limit parameter",
                    "detail": "limit must be an integer between 1 and 20",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Default to 1 - show all paths, even unique ones
            min_sessions = int(request.query_params.get("min_sessions", 1))
            min_sessions = max(1, min_sessions)  # At least 1
        except (ValueError, TypeError):
            return Response(
                {
                    "error": "Invalid min_sessions parameter",
                    "detail": "min_sessions must be a positive integer",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            max_path_length = int(request.query_params.get("max_path_length", 10))
            max_path_length = min(max(2, max_path_length), 50)  # Clamp between 2 and 50
        except (ValueError, TypeError):
            return Response(
                {
                    "error": "Invalid max_path_length parameter",
                    "detail": "max_path_length must be an integer between 2 and 50",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse date filters
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        tz_name = request.query_params.get("tz", "UTC")

        # Parse dates with timezone awareness
        try:
            start_datetime, end_datetime = parse_date_range(start_date, end_date, tz_name)
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Build base queryset
        events_qs = Event.objects.filter(app=app)

        if start_datetime:
            events_qs = events_qs.filter(timestamp__gte=start_datetime)
        if end_datetime:
            events_qs = events_qs.filter(timestamp__lte=end_datetime)

        # PERF-009: Check cache before running expensive analysis
        import hashlib

        from django.conf import settings
        from django.core.cache import cache

        grouping = event_groups.from_request(request, app)
        cache_params = (
            f"{','.join(sorted(conversion_events))}:{start_date}:{end_date}:"
            f"{limit}:{min_sessions}:{max_path_length}:{tz_name}:{grouping.key()}"
        )
        cache_hash = hashlib.md5(cache_params.encode()).hexdigest()[:16]
        cache_key = f"conversion_paths:{app.id}:{cache_hash}"

        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return Response(cached_result, status=status.HTTP_200_OK)

        # Calculate conversion paths (session-based)
        analysis_result = self._discover_conversion_paths(
            app,
            events_qs,
            conversion_events,
            limit=limit,
            min_sessions=min_sessions,
            max_path_length=max_path_length,
            grouping=grouping,
            slices=slices_in(app, start_datetime, end_datetime),
        )

        # Add small sample warning if sessions are low
        total_converting = analysis_result["data_quality"].get("total_converting_sessions", 0)
        small_sample_warning = None
        if 0 < total_converting < 10:
            small_sample_warning = (
                f"Small sample size: {total_converting} converting "
                f"session{'s' if total_converting != 1 else ''}. Results may vary with more data."
            )

        # Enrich data_quality with warning
        data_quality = analysis_result["data_quality"]
        data_quality["small_sample_warning"] = small_sample_warning

        response_data = {
            "app": {"id": app.id, "name": app.name, "slug": app.slug},
            "filters": {
                "conversion_events": conversion_events,
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit,
                "min_sessions": min_sessions,
                "max_path_length": max_path_length,
                "group_events": bool(grouping.groups),
            },
            "data_quality": data_quality,
            "top_conversion_paths": analysis_result["paths"],
            "interpretation": (
                "These paths show what sessions do before they convert. Each session is analyzed "
                "independently."
            ),
        }

        # PERF-009: Cache the result for 3 minutes
        cache.set(cache_key, response_data, timeout=settings.CACHE_TTL_CONVERSION)

        return Response(response_data, status=status.HTTP_200_OK)

    def _discover_conversion_paths(
        self,
        app,
        events_qs,
        conversion_events,
        limit=5,
        min_sessions=1,
        max_path_length=10,
        grouping=event_groups.NONE,
        *,
        slices,
    ):
        """
        The most common paths converting sessions took, walked and counted in one SQL query.

        A converting session's path is its events up to its first conversion event, each name
        read through the groups, a step that repeats the one before dropped, the last
        `max_path_length` kept. The database counts the paths and averages their timings, and
        returns only the top `limit`, so the rows that come back do not grow with the sessions
        (conversion/test_bounded_reads.py holds it to the Python walk it replaced).

        Returns:
            dict with 'data_quality' and 'paths' keys
        """
        from django.db import connection

        empty = {
            "total_converting_sessions": 0,
            "paths_analyzed": 0,
            "unique_paths_found": 0,
        }
        conversion_events_list = list(conversion_events)
        if not conversion_events_list:
            return {"data_quality": empty, "paths": []}

        base_sql, base_params = base_events(events_qs)
        slice_sql, slice_params = slices.order_by().values("session_id").query.sql_with_params()
        conversion_placeholders = ",".join(["%s"] * len(conversion_events_list))
        name_sql, name_params = grouping.sql("e.event_name")

        sql = f"""
        WITH base_events AS NOT MATERIALIZED ({base_sql}),
        first_conversions AS (
            SELECT session_id, MIN(timestamp) AS first_conversion_time
            FROM base_events
            WHERE event_name IN ({conversion_placeholders})
                AND session_id IS NOT NULL AND session_id != ''
            GROUP BY session_id
        ),
        -- Every session of the range, from its slices (analytics.SessionSlice), counted by hash
        all_sessions AS (
            SELECT COUNT(*) AS total_sessions
            FROM (
                SELECT session_id COLLATE "C" FROM ({slice_sql}) s
                WHERE session_id IS NOT NULL AND session_id != ''
                GROUP BY 1
            ) s
        ),
        walked AS (
            SELECT e.session_id, {name_sql} AS name, e.timestamp,
                e.event_name IN ({conversion_placeholders}) AS converts,
                ROW_NUMBER() OVER (PARTITION BY e.session_id ORDER BY e.timestamp) AS rn
            FROM base_events e
            JOIN first_conversions fc ON e.session_id = fc.session_id
            WHERE e.timestamp <= fc.first_conversion_time
        ),
        -- ending at the first conversion event
        cut AS (
            SELECT session_id, name, timestamp, rn,
                MIN(rn) FILTER (WHERE converts) OVER (PARTITION BY session_id) AS stop
            FROM walked
        ),
        -- a step that repeats the one before is dropped
        steps AS (
            SELECT session_id, name, timestamp, rn,
                name IS DISTINCT FROM LAG(name) OVER (PARTITION BY session_id ORDER BY rn)
                    AS new_step
            FROM cut
            WHERE rn <= stop
        ),
        walks AS (
            SELECT session_id,
                array_agg(name ORDER BY rn) AS names,
                array_agg(timestamp ORDER BY rn) AS times
            FROM steps
            WHERE new_step
            GROUP BY session_id
        ),
        -- the last max_path_length steps
        kept AS (
            SELECT names[greatest(1, cardinality(names) - %s + 1):] AS names,
                times[greatest(1, cardinality(times) - %s + 1):] AS times
            FROM walks
        ),
        counted AS (
            SELECT names, COUNT(*) AS sessions,
                AVG(EXTRACT(EPOCH FROM times[cardinality(times)] - times[1])::float8)
                    FILTER (WHERE cardinality(times) >= 2) AS duration
            FROM kept
            GROUP BY names
        ),
        top AS (
            SELECT names, sessions, duration
            FROM counted
            WHERE sessions >= %s
            ORDER BY sessions DESC, names
            LIMIT %s
        ),
        gaps AS (
            SELECT k.names, g.i,
                AVG(EXTRACT(EPOCH FROM k.times[g.i + 1] - k.times[g.i])::float8) AS gap
            FROM kept k
            JOIN top t ON t.names = k.names
            CROSS JOIN LATERAL generate_subscripts(k.times, 1) AS g(i)
            WHERE g.i < cardinality(k.times)
            GROUP BY k.names, g.i
        ),
        totals AS (
            SELECT (SELECT COUNT(*) FROM kept) AS converting,
                (SELECT COUNT(*) FROM counted) AS unique_paths,
                (SELECT total_sessions FROM all_sessions) AS total_sessions
        )
        SELECT totals.converting, totals.unique_paths, totals.total_sessions,
            t.names, t.sessions, t.duration,
            (SELECT array_agg(g.gap ORDER BY g.i) FROM gaps g WHERE g.names = t.names)
        FROM totals
        LEFT JOIN top t ON true
        ORDER BY t.sessions DESC NULLS LAST, t.names
        """
        params = [
            *base_params,
            *conversion_events_list,
            *slice_params,
            *name_params,
            *conversion_events_list,
            max_path_length,
            max_path_length,
            min_sessions,
            limit,
        ]
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        converting, unique_paths, total_sessions = rows[0][:3]
        total_sessions = total_sessions or 0
        if not converting:
            return {"data_quality": empty, "paths": []}
        found = {
            "total_converting_sessions": converting,
            "paths_analyzed": converting,
            "unique_paths_found": unique_paths,
        }
        top = [row for row in rows if row[3] is not None]
        if not top:
            return {"data_quality": found, "paths": []}

        result_paths = []
        for rank, (*_, names, sessions, duration, gaps) in enumerate(top, 1):
            names = list(names)
            conversion_rate = sessions / total_sessions if total_sessions > 0 else 0
            step_timings = [
                {"from": names[i], "to": names[i + 1], "avg_minutes": round(gap / 60.0, 2)}
                for i, gap in enumerate(gaps or [])
            ]
            result_paths.append(
                {
                    "rank": rank,
                    "path": names,
                    "sessions": sessions,
                    "conversion_rate": round(conversion_rate, 4),
                    "avg_duration_minutes": round(duration / 60.0, 2) if duration else 0,
                    "step_timings": step_timings,
                }
            )

        return {
            "data_quality": {
                **found,
                "total_unique_paths": unique_paths,  # Alias for frontend compatibility
            },
            "paths": result_paths,
        }


class DropOffView(APIView):
    """
    GET /api/v1/analytics/drop-off/ - Drop-Off Diagnostics

    Identifies where non-converting sessions end by comparing the behavior
    of converting vs non-converting sessions. This helps identify which
    events or stages are "killing" conversions within sessions.

    This is a **session-based** analysis. Each session is analyzed independently
    to understand where sessions end without converting.

    Query Parameters:
        conversion_events (required): Comma-separated list of event names to
            count as conversion events (e.g., "purchase,subscription_start")
        min_sessions (optional): Minimum number of sessions for a drop-off point to
            be included (default: 5, helps filter noise)
        limit (optional): Maximum number of drop-off points to return
            (default: 10, max: 50)
        start_date (optional): Filter events from this date (YYYY-MM-DD)
        end_date (optional): Filter events to this date (YYYY-MM-DD)

    Returns:
        200 OK: Drop-off points with diagnostics
        400 Bad Request: If conversion_events is missing or invalid parameters

    Algorithm:
        1. Identify all sessions with a conversion event
        2. Identify all sessions without a conversion event
        3. For non-converting sessions, find their "last event before exit"
        4. Rank events by drop-off frequency
        5. Calculate drop-off rate and compare to converting session behavior
    """

    share_links = True  # a share link's dashboard reads it (teams/)
    authentication_classes = APP_OWNER
    permission_classes = [HasValidAppKey]

    @swagger_auto_schema(
        operation_summary="Get drop-off diagnostics",
        operation_description="""
Identify where non-converting sessions end.

**Required Parameter:**
- `conversion_events`: Comma-separated event names (e.g., "purchase,subscription_start")

**What This Endpoint Does:**
1. Finds all sessions that did NOT include a conversion event
2. Identifies their "last event before session end" (where they dropped off)
3. Ranks events by drop-off frequency
4. Compares non-converting vs converting session behavior patterns
5. Calculates impact scores to prioritize fixes

**Session-Based Analysis:**
- Each session is analyzed independently (no cross-session tracking)
- Shows where sessions end without converting
- Maximum session duration is ~2 hours

**Use Cases:**
- Find which features are causing sessions to end without converting
- Identify friction points in the onboarding flow
- Prioritize UX improvements for conversion impact
- Compare where converting vs non-converting sessions spend time
        """,
        manual_parameters=[
            GROUP_EVENTS,
            openapi.Parameter(
                "conversion_events",
                openapi.IN_QUERY,
                description="REQUIRED: Comma-separated event names to count as conversions",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "min_sessions",
                openapi.IN_QUERY,
                description="Minimum sessions for a drop-off point to be included (default: 5)",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="Maximum number of drop-off points to return (default: 10, max: 50)",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                description="Start date filter (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                description="End date filter (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
            ),
            openapi.Parameter(
                "tz",
                openapi.IN_QUERY,
                description=(
                    "IANA timezone name (e.g., 'America/New_York', 'Europe/London'). Dates are "
                    "interpreted in this timezone. Defaults to UTC."
                ),
                type=openapi.TYPE_STRING,
                required=False,
                default="UTC",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Drop-off diagnostics with ranked problem areas",
                examples={
                    "application/json": {
                        "app": {"id": 1, "name": "My App", "slug": "my-app"},
                        "filters": {
                            "conversion_events": ["purchase"],
                            "start_date": None,
                            "end_date": None,
                            "min_sessions": 5,
                            "limit": 10,
                        },
                        "data_quality": {
                            "total_sessions": 500,
                            "converting_sessions": 150,
                            "non_converting_sessions": 350,
                            "conversion_rate": 0.30,
                        },
                        "drop_off_points": [
                            {
                                "rank": 1,
                                "event": "pricing_view",
                                "sessions_dropped": 89,
                                "drop_off_rate": 0.25,
                                "avg_time_before_exit_minutes": 2.5,
                                "impact_score": 0.85,
                                "converter_comparison": {
                                    "converters_with_event": 120,
                                    "converters_event_rate": 0.80,
                                    "non_converters_event_rate": 0.45,
                                    "differential": -0.35,
                                },
                            }
                        ],
                        "events_more_common_in_non_converters": [
                            {
                                "event": "support_contact",
                                "non_converter_rate": 0.35,
                                "converter_rate": 0.08,
                                "differential": 0.27,
                            }
                        ],
                        "interpretation": (
                            "Sessions that don't convert - where do they end? Each session is "
                            "analyzed independently."
                        ),
                    }
                },
            ),
            400: openapi.Response(description="Missing or invalid parameters"),
            401: openapi.Response(description="Unauthorized - missing or invalid app_key"),
        },
        tags=["Analytics"],
    )
    def get(self, request):
        """
        Get drop-off diagnostics for an application.
        """
        # Get the authenticated app
        app = request.user

        # Validate required parameters
        conversion_events_param = request.query_params.get("conversion_events")

        if not conversion_events_param:
            # Get user's actual event types to help them
            event_types = list(
                Event.objects.filter(app=app)
                .values_list("event_name", flat=True)
                .distinct()
                .order_by("event_name")[:20]
            )
            return Response(
                {
                    "error": "conversion_events parameter is required",
                    "detail": "Please specify which events to count as conversions.",
                    "your_event_types": event_types,
                    "example": "?conversion_events="
                    + (
                        ",".join(event_types[:2])
                        if len(event_types) >= 2
                        else "purchase,subscription"
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse conversion events
        conversion_events = [e.strip() for e in conversion_events_param.split(",") if e.strip()]

        if not conversion_events:
            return Response(
                {
                    "error": "conversion_events parameter is empty",
                    "detail": "Please specify at least one event name.",
                    "example": "?conversion_events=purchase,subscription",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse optional parameters
        try:
            min_sessions = int(request.query_params.get("min_sessions", 5))
            min_sessions = max(1, min_sessions)  # At least 1
        except (ValueError, TypeError):
            return Response(
                {
                    "error": "Invalid min_sessions parameter",
                    "detail": "min_sessions must be a positive integer",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            limit = int(request.query_params.get("limit", 10))
            limit = min(max(1, limit), 50)  # Clamp between 1 and 50
        except (ValueError, TypeError):
            return Response(
                {
                    "error": "Invalid limit parameter",
                    "detail": "limit must be an integer between 1 and 50",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse date filters
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        tz_name = request.query_params.get("tz", "UTC")

        # Parse dates with timezone awareness
        try:
            start_datetime, end_datetime = parse_date_range(start_date, end_date, tz_name)
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Build base queryset
        events_qs = Event.objects.filter(app=app)

        if start_datetime:
            events_qs = events_qs.filter(timestamp__gte=start_datetime)
        if end_datetime:
            events_qs = events_qs.filter(timestamp__lte=end_datetime)

        # PERF-009: Check cache before running expensive analysis
        import hashlib

        from django.conf import settings
        from django.core.cache import cache

        grouping = event_groups.from_request(request, app)
        cache_params = (
            f"{','.join(sorted(conversion_events))}:{start_date}:{end_date}:"
            f"{min_sessions}:{limit}:{tz_name}:{grouping.key()}"
        )
        cache_hash = hashlib.md5(cache_params.encode()).hexdigest()[:16]
        cache_key = f"drop_off:{app.id}:{cache_hash}"

        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return Response(cached_result, status=status.HTTP_200_OK)

        # Calculate drop-off diagnostics (session-based)
        analysis_result = self._analyze_drop_offs(
            app,
            slices_in(app, start_datetime, end_datetime),
            conversion_events,
            min_sessions=min_sessions,
            limit=limit,
            grouping=grouping,
        )

        response_data = {
            "app": {"id": app.id, "name": app.name, "slug": app.slug},
            "filters": {
                "conversion_events": conversion_events,
                "start_date": start_date,
                "end_date": end_date,
                "min_sessions": min_sessions,
                "limit": limit,
                "group_events": bool(grouping.groups),
            },
            "data_quality": analysis_result["data_quality"],
            "drop_off_points": analysis_result["drop_off_points"],
            "events_more_common_in_non_converters": analysis_result["differential_events"],
            "interpretation": (
                "Sessions that don't convert - where do they end? Each session is analyzed "
                "independently."
            ),
        }

        # PERF-009: Cache the result for 3 minutes
        cache.set(cache_key, response_data, timeout=settings.CACHE_TTL_CONVERSION)

        return Response(response_data, status=status.HTTP_200_OK)

    def _analyze_drop_offs(
        self,
        app,
        slices,
        conversion_events,
        min_sessions=5,
        limit=10,
        grouping=event_groups.NONE,
    ):
        """
        Where sessions that did not convert stopped, and which events they hit more often than
        converting sessions, in one SQL query.

        It reads the range's session slices (analytics.SessionSlice, `slices`), a row or two per
        session instead of every event: each session (did it convert, its first and last
        moment, its last event), the events each session hit, then the sessions that stopped at
        each event and how long after their first, and how many converting and other sessions
        hit each event. The rows that come back are one per event name, whatever the number of
        sessions (conversion/test_bounded_reads.py holds it to the readings it replaced).

        With the app's groups (`grouping`), every event is read as its group in SQL, before
        sessions are counted, so a session that sent purchase_light and purchase_pro counts once
        for purchase, and a group is held to `min_sessions` as a whole.

        Returns:
            dict with 'data_quality', 'drop_off_points', and 'differential_events'
        """
        from django.db import connection

        slice_sql, slice_params = (
            slices.order_by()
            .filter(session_id__isnull=False)
            .exclude(session_id="")
            .values("session_id", "names", "first_at", "last_at", "last_name")
            .query.sql_with_params()
        )
        # Each event as its group, and the names a conversion event reads as
        name_sql, name_params = grouping.sql("n")
        last_sql, last_params = grouping.sql("substr(last_key, 21)")
        conversion_names = {grouping.label(e) for e in conversion_events}

        sql = f"""
        -- Read once per use rather than copied to disk, session ids compared byte for byte
        WITH slices AS NOT MATERIALIZED (
            SELECT x.session_id COLLATE "C" AS session_id, x.names, x.first_at, x.last_at,
                x.last_name
            FROM ({slice_sql}) x
        ),
        -- A session's last event: the moment, as fixed-width text, then the name, so the
        -- greatest key over its slices holds it
        sessions AS (
            SELECT session_id, bool_or(names && %s::varchar[]) AS converted,
                MIN(first_at) AS first_at, MAX(last_at) AS last_at,
                MAX(to_char(last_at AT TIME ZONE 'UTC', 'YYYYMMDDHH24MISSUS')
                    || last_name COLLATE "C") AS last_key
            FROM slices
            GROUP BY session_id
        ),
        -- The sessions in one pass: all of them, the converting ones, and those that stopped
        -- at each event and how long after their first
        ended AS (
            SELECT CASE WHEN converted THEN NULL ELSE {last_sql} END AS name, converted,
                COUNT(*) AS sessions,
                AVG(NULLIF(EXTRACT(EPOCH FROM (last_at - first_at))::float8, 0)) AS seconds
            FROM sessions
            GROUP BY 1, 2
        ),
        -- Each session's events, in session order, with whether the session converted read in
        -- the same pass, so nothing is joined back
        pairs AS (
            SELECT s.session_id, {name_sql} AS name, bool_or(n = ANY(%s::varchar[])) AS converts
            FROM slices s CROSS JOIN LATERAL unnest(s.names) AS n
            GROUP BY 1, 2
        ),
        presence AS (
            SELECT name, COUNT(*) FILTER (WHERE converted) AS converters,
                COUNT(*) FILTER (WHERE NOT converted) AS others
            FROM (
                SELECT name, bool_or(converts) OVER (PARTITION BY session_id) AS converted
                FROM pairs
            ) flagged
            GROUP BY name
        ),
        totals AS (
            SELECT SUM(sessions)::bigint AS sessions,
                (SUM(sessions) FILTER (WHERE converted))::bigint AS converting
            FROM ended
        ),
        dropped AS (
            SELECT name, sessions AS sessions_dropped, seconds FROM ended WHERE NOT converted
        )
        SELECT totals.sessions, totals.converting, presence.name, presence.converters,
            presence.others, dropped.sessions_dropped, dropped.seconds
        FROM totals
        LEFT JOIN presence ON true
        LEFT JOIN dropped ON dropped.name = presence.name
        """
        conversions = list(conversion_events)
        params = [*slice_params, conversions, *last_params, *name_params, conversions]
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        total_sessions = rows[0][0] or 0
        converting_sessions_count = rows[0][1] or 0
        non_converting_sessions_count = total_sessions - converting_sessions_count
        conversion_rate = converting_sessions_count / total_sessions if total_sessions > 0 else 0.0

        if total_sessions == 0:
            return {
                "data_quality": {
                    "total_sessions": 0,
                    "converting_sessions": 0,
                    "non_converting_sessions": 0,
                    "conversion_rate": 0.0,
                },
                "drop_off_points": [],
                "differential_events": [],
            }

        if non_converting_sessions_count == 0:
            return {
                "data_quality": {
                    "total_sessions": total_sessions,
                    "converting_sessions": converting_sessions_count,
                    "non_converting_sessions": 0,
                    "conversion_rate": round(conversion_rate, 4),
                },
                "drop_off_points": [],
                "differential_events": [],
            }

        converter_event_counts = {row[2]: row[3] or 0 for row in rows if row[2] is not None}
        non_converter_event_counts = {row[2]: row[4] or 0 for row in rows if row[2] is not None}
        last_event_rows = [(row[2], row[5], row[6]) for row in rows if row[5]]

        # =========================================================================
        # Build drop-off points list (session-based)
        # =========================================================================
        drop_off_points = []

        for event_name, sessions_dropped, avg_seconds in last_event_rows:
            if sessions_dropped < min_sessions:
                continue

            # Skip if the drop-off event is a conversion event (these aren't really drop-offs)
            if event_name in conversion_names:
                continue

            drop_off_rate = (
                sessions_dropped / non_converting_sessions_count
                if non_converting_sessions_count > 0
                else 0
            )

            # Average time before exit
            avg_time_before_exit_minutes = avg_seconds / 60.0 if avg_seconds else 0

            # Calculate converter comparison
            converters_with_event = converter_event_counts.get(event_name, 0)
            non_converters_with_event = non_converter_event_counts.get(event_name, 0)

            converters_event_rate = (
                converters_with_event / converting_sessions_count
                if converting_sessions_count > 0
                else 0
            )
            non_converters_event_rate = (
                non_converters_with_event / non_converting_sessions_count
                if non_converting_sessions_count > 0
                else 0
            )

            # Impact score: higher means more impactful drop-off point
            # Combines drop-off frequency with differential
            # (how much less converters hit this event)
            differential = non_converters_event_rate - converters_event_rate
            impact_score = drop_off_rate * (
                1 + max(0, differential)
            )  # Boost if event is more common in non-converters

            drop_off_points.append(
                {
                    "event": event_name,
                    "sessions_dropped": sessions_dropped,
                    "drop_off_rate": round(drop_off_rate, 4),
                    "avg_time_before_exit_minutes": round(avg_time_before_exit_minutes, 2),
                    "impact_score": round(impact_score, 4),
                    "converter_comparison": {
                        "converters_with_event": converters_with_event,
                        "converters_event_rate": round(converters_event_rate, 4),
                        "non_converters_event_rate": round(non_converters_event_rate, 4),
                        "differential": round(differential, 4),
                    },
                }
            )

        # Sort by sessions_dropped (frequency) - most common drop-off points first
        # This is intuitive: higher sessions = more users abandoning at this point
        drop_off_points.sort(key=lambda x: x["sessions_dropped"], reverse=True)

        for rank, point in enumerate(drop_off_points[:limit], 1):
            point["rank"] = rank

        # Build events more common in non-converters list
        all_events = set(converter_event_counts.keys()) | set(non_converter_event_counts.keys())
        differential_events = []

        for event_name in all_events:
            if event_name in conversion_names:
                continue  # Skip conversion events themselves

            converters_rate = (
                converter_event_counts.get(event_name, 0) / converting_sessions_count
                if converting_sessions_count > 0
                else 0
            )
            non_converters_rate = (
                non_converter_event_counts.get(event_name, 0) / non_converting_sessions_count
                if non_converting_sessions_count > 0
                else 0
            )

            differential = non_converters_rate - converters_rate

            # Only include events that are more common in non-converters
            if differential > 0.05:  # At least 5% difference
                differential_events.append(
                    {
                        "event": event_name,
                        "non_converter_rate": round(non_converters_rate, 4),
                        "converter_rate": round(converters_rate, 4),
                        "differential": round(differential, 4),
                    }
                )

        # Sort by differential (most different first)
        differential_events.sort(key=lambda x: x["differential"], reverse=True)

        return {
            "data_quality": {
                "total_sessions": total_sessions,
                "converting_sessions": converting_sessions_count,
                "non_converting_sessions": non_converting_sessions_count,
                "conversion_rate": round(conversion_rate, 4),
            },
            "drop_off_points": drop_off_points[:limit],
            "differential_events": differential_events[:10],  # Top 10 differential events
        }


class EventCorrelationView(APIView):
    """
    GET /api/v1/analytics/event-correlation/ - Conversion Drivers Map

    Identifies which events correlate positively or negatively with conversion.
    Shows high- and low-impact events with lift scores to help developers
    understand which features drive conversions.

    This is a **session-based** analysis. Each session is analyzed independently
    to determine which events correlate with conversion within that session.

    Query Parameters:
        conversion_events (required): Comma-separated list of event names to
            count as conversion events (e.g., "purchase,subscription_start")
        min_sessions (optional): Minimum sessions that have an event for it to
            be included (default: 10, helps filter noise and ensure significance)
        limit (optional): Maximum events to return per category (default: 10, max: 50)
        start_date (optional): Filter events from this date (YYYY-MM-DD)
        end_date (optional): Filter events to this date (YYYY-MM-DD)

    Returns:
        200 OK: Event correlations with lift scores
        400 Bad Request: If conversion_events is missing or invalid parameters

    Algorithm:
        1. Get all sessions
        2. Identify converting and non-converting sessions
        3. For each event type:
           a. Calculate conversion rate of sessions that included the event
           b. Calculate conversion rate of sessions that did NOT include the event
           c. Calculate lift: (rate_with / rate_without - 1) * 100
        4. Separate into positive and negative correlations
        5. Rank by absolute lift value
    """

    share_links = True  # a share link's dashboard reads it (teams/)
    authentication_classes = APP_OWNER
    permission_classes = [HasValidAppKey]

    # Minimum sessions required for an event to be included in correlation analysis
    # Shows filtered count in response so users know when events are excluded
    DEFAULT_MIN_SESSIONS = 10

    @swagger_auto_schema(
        operation_summary="Get event correlation analysis (Conversion Drivers)",
        operation_description="""
Identify which events correlate with conversion (positive or negative lift).

**Required Parameter:**
- `conversion_events`: Comma-separated event names (e.g., "purchase,subscription_start")

**What This Endpoint Does:**
1. For each event type, calculates conversion rate of sessions that include it vs don't
2. Computes lift score: `(rate_with / rate_without - 1) × 100`
3. Separates events into positive correlation (boost conversion) and negative correlation
   (hurt conversion)
4. Ranks by absolute lift value

**Lift Score Interpretation:**
- `+245%` means sessions with this event are 3.45x more likely to convert
- `-67%` means sessions with this event are 67% less likely to convert
- `0%` means no correlation with conversion

**Session-Based Analysis:**
- Each session is analyzed independently (no cross-session tracking)
- Minimum 10 sessions per event by default (configurable)
- Maximum session duration is ~2 hours

**Use Cases:**
- Find which in-session behaviors drive conversions
- Identify features that correlate with session abandonment
- Prioritize feature development based on conversion impact
- A/B test validation: does new feature improve conversion?
        """,
        manual_parameters=[
            GROUP_EVENTS,
            openapi.Parameter(
                "conversion_events",
                openapi.IN_QUERY,
                description="REQUIRED: Comma-separated event names to count as conversions",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "min_sessions",
                openapi.IN_QUERY,
                description="Minimum sessions for an event to be included (default: 10)",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="Maximum events per category (default: 10, max: 50)",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                description="Start date filter (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                description="End date filter (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
            ),
            openapi.Parameter(
                "tz",
                openapi.IN_QUERY,
                description=(
                    "IANA timezone name (e.g., 'America/New_York', 'Europe/London'). Dates are "
                    "interpreted in this timezone. Defaults to UTC."
                ),
                type=openapi.TYPE_STRING,
                required=False,
                default="UTC",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Event correlation analysis with lift scores",
                examples={
                    "application/json": {
                        "app": {"id": 1, "name": "My App", "slug": "my-app"},
                        "filters": {
                            "conversion_events": ["purchase"],
                            "start_date": None,
                            "end_date": None,
                            "min_sessions": 10,
                            "limit": 10,
                        },
                        "data_quality": {
                            "total_sessions": 500,
                            "converting_sessions": 150,
                            "non_converting_sessions": 350,
                            "baseline_conversion_rate": 0.30,
                            "events_analyzed": 15,
                        },
                        "positive_correlations": [
                            {
                                "rank": 1,
                                "event": "feature_demo",
                                "lift_percent": 245.5,
                                "sessions_with_event": 456,
                                "sessions_without_event": 44,
                                "conversion_rate_with": 0.52,
                                "conversion_rate_without": 0.15,
                                "converts_with": 237,
                                "converts_without": 7,
                            }
                        ],
                        "negative_correlations": [
                            {
                                "rank": 1,
                                "event": "error_screen",
                                "lift_percent": -67.3,
                                "sessions_with_event": 123,
                                "sessions_without_event": 377,
                                "conversion_rate_with": 0.11,
                                "conversion_rate_without": 0.34,
                                "converts_with": 14,
                                "converts_without": 128,
                            }
                        ],
                        "neutral_events": ["app_open", "screen_view"],
                        "interpretation": (
                            "Sessions that include X: correlation with conversion. Each session "
                            "analyzed independently."
                        ),
                    }
                },
            ),
            400: openapi.Response(description="Missing or invalid parameters"),
            401: openapi.Response(description="Unauthorized - missing or invalid app_key"),
        },
        tags=["Analytics"],
    )
    def get(self, request):
        """
        Get event correlation analysis for an application.
        """
        # Get the authenticated app
        app = request.user

        # Validate required parameters
        conversion_events_param = request.query_params.get("conversion_events")

        if not conversion_events_param:
            # Get user's actual event types to help them
            event_types = list(
                Event.objects.filter(app=app)
                .values_list("event_name", flat=True)
                .distinct()
                .order_by("event_name")[:20]
            )
            return Response(
                {
                    "error": "conversion_events parameter is required",
                    "detail": "Please specify which events to count as conversions.",
                    "your_event_types": event_types,
                    "example": "?conversion_events="
                    + (
                        ",".join(event_types[:2])
                        if len(event_types) >= 2
                        else "purchase,subscription"
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse conversion events
        conversion_events = [e.strip() for e in conversion_events_param.split(",") if e.strip()]

        if not conversion_events:
            return Response(
                {
                    "error": "conversion_events parameter is empty",
                    "detail": "Please specify at least one event name.",
                    "example": "?conversion_events=purchase,subscription",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse optional parameters
        try:
            min_sessions = int(request.query_params.get("min_sessions", self.DEFAULT_MIN_SESSIONS))
            min_sessions = max(1, min_sessions)  # At least 1
        except (ValueError, TypeError):
            return Response(
                {
                    "error": "Invalid min_sessions parameter",
                    "detail": "min_sessions must be a positive integer",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            limit = int(request.query_params.get("limit", 10))
            limit = min(max(1, limit), 50)  # Clamp between 1 and 50
        except (ValueError, TypeError):
            return Response(
                {
                    "error": "Invalid limit parameter",
                    "detail": "limit must be an integer between 1 and 50",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse date filters
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        tz_name = request.query_params.get("tz", "UTC")

        # Parse dates with timezone awareness
        try:
            start_datetime, end_datetime = parse_date_range(start_date, end_date, tz_name)
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST
            )

        # PERF-013: Check cache before running expensive analysis
        import hashlib

        from django.conf import settings
        from django.core.cache import cache

        grouping = event_groups.from_request(request, app)
        cache_params = (
            f"{','.join(sorted(conversion_events))}:{start_date}:{end_date}:"
            f"{min_sessions}:{limit}:{tz_name}:{grouping.key()}"
        )
        cache_hash = hashlib.md5(cache_params.encode()).hexdigest()[:16]
        cache_key = f"event_correlation:{app.id}:{cache_hash}"

        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return Response(cached_result, status=status.HTTP_200_OK)

        # Build base queryset
        events_qs = Event.objects.filter(app=app)

        if start_datetime:
            events_qs = events_qs.filter(timestamp__gte=start_datetime)
        if end_datetime:
            events_qs = events_qs.filter(timestamp__lte=end_datetime)

        # Calculate event correlations (session-based)
        analysis_result = self._analyze_event_correlations(
            app,
            slices_in(app, start_datetime, end_datetime),
            conversion_events,
            min_sessions=min_sessions,
            limit=limit,
            grouping=grouping,
        )

        response_data = {
            "app": {"id": app.id, "name": app.name, "slug": app.slug},
            "filters": {
                "conversion_events": conversion_events,
                "start_date": start_date,
                "end_date": end_date,
                "min_sessions": min_sessions,
                "limit": limit,
                "group_events": bool(grouping.groups),
            },
            "data_quality": analysis_result["data_quality"],
            "positive_correlations": analysis_result["positive_correlations"],
            "negative_correlations": analysis_result["negative_correlations"],
            "neutral_events": analysis_result["neutral_events"],
            "interpretation": (
                "Sessions that include X: correlation with conversion. Each session analyzed "
                "independently."
            ),
        }

        # PERF-013: Cache the result (3 min TTL)
        cache.set(cache_key, response_data, timeout=settings.CACHE_TTL_CONVERSION)

        return Response(response_data, status=status.HTTP_200_OK)

    def _analyze_event_correlations(
        self,
        app,
        slices,
        conversion_events,
        min_sessions=10,
        limit=10,
        grouping=event_groups.NONE,
    ):
        """
        PERF-011 & PERF-FIX: Optimized event correlation analysis using SQL (session-based).

        Previous implementation: Loaded all session IDs into Python sets (memory issue)
        New implementation: Uses pure SQL for all aggregations and calculations

        Algorithm:
        1. Use SQL to get counts directly (total sessions, converting sessions)
        2. Use SQL to compute correlation stats per event type in single query
        3. No session IDs are ever loaded into Python memory

        With the app's groups (`grouping`), each event is read as its group before a session's
        events are made distinct, so a session counts once for a group, and a group that holds a
        conversion event is left out with it.

        Returns:
            dict with 'data_quality', 'positive_correlations',
            'negative_correlations', 'neutral_events'
        """
        from django.db import connection

        # PERF-FIX: Get the SQL and params from the Django queryset (for base filtering)
        # The range's session slices (analytics.SessionSlice): the event names each session holds
        slice_sql, slice_params = (
            slices.order_by()
            .filter(session_id__isnull=False)
            .exclude(session_id="")
            .values("session_id", "names")
            .query.sql_with_params()
        )

        # Build conversion events placeholder for SQL
        conversion_placeholders = ", ".join(["%s"] * len(conversion_events))
        # Each event as its group; the events left out: the conversion events and every event
        # of a group that holds one
        name_sql, name_params = grouping.sql("n")
        left_out = grouping.expand({grouping.label(e) for e in conversion_events})
        left_out_placeholders = ", ".join(["%s"] * len(left_out))

        # =========================================================================
        # Single query that computes everything in SQL:
        # - Total sessions and converting sessions counts
        # - For each non-conversion event: sessions with/without, converters with/without
        # =========================================================================

        # One pass over the range's session slices: each session's event names as (session,
        # event) pairs, whether the pair holds a conversion event; the sessions from the pairs;
        # then per event, the sessions with it and the converting ones among them. The events
        # left out are counted for no event, but their sessions still count, and convert.
        correlation_sql = f"""
        -- Read once per use rather than copied to disk, session ids compared byte for byte
        WITH slices AS NOT MATERIALIZED (
            SELECT x.session_id COLLATE "C" AS session_id, x.names FROM ({slice_sql}) x
        ),
        pairs AS (
            SELECT s.session_id, {name_sql} AS event_name,
                bool_or(n IN ({conversion_placeholders})) AS converts,
                bool_or(n NOT IN ({left_out_placeholders})) AS counted
            FROM slices s CROSS JOIN LATERAL unnest(s.names) AS n
            GROUP BY 1, 2
        ),
        -- The pairs come out in session order, so whether a session converted, and its first
        -- pair (to count it once), are read in that same pass, with no join back
        flagged AS (
            SELECT event_name, counted,
                bool_or(converts) OVER per_session AS converted,
                row_number() OVER per_session = 1 AS first_of_session
            FROM pairs
            WINDOW per_session AS (PARTITION BY session_id)
        ),
        per_event AS (
            SELECT event_name,
                COUNT(*) FILTER (WHERE counted) AS sessions_with_event,
                COUNT(*) FILTER (WHERE counted AND converted) AS converters_with_event,
                (SUM(COUNT(*) FILTER (WHERE first_of_session)) OVER ())::bigint
                    AS total_sessions,
                (SUM(COUNT(*) FILTER (WHERE first_of_session AND converted)) OVER ())::bigint
                    AS converting_sessions
            FROM flagged
            GROUP BY event_name
        ),
        counted AS (
            SELECT *, COUNT(*) OVER () AS total_event_types
            FROM per_event
            WHERE sessions_with_event > 0
        )
        SELECT
            event_name,
            sessions_with_event,
            (total_sessions - sessions_with_event) AS sessions_without_event,
            converters_with_event,
            (converting_sessions - converters_with_event) AS converters_without_event,
            total_sessions,
            converting_sessions,
            total_event_types
        FROM counted
        WHERE sessions_with_event >= %s
            AND (total_sessions - sessions_with_event) >= %s
        """

        # Parameters, in the order they appear: base_params + the group names + the conversion
        # events + the events left out + min_sessions + min_sessions
        params = (
            list(slice_params)
            + name_params
            + list(conversion_events)
            + left_out
            + [min_sessions, min_sessions]
        )

        with connection.cursor() as cursor:
            cursor.execute(correlation_sql, params)
            rows = cursor.fetchall()

        if not rows:
            return {
                "data_quality": {
                    "total_sessions": 0,
                    "converting_sessions": 0,
                    "non_converting_sessions": 0,
                    "baseline_conversion_rate": 0.0,
                    "events_analyzed": 0,
                    "events_filtered_out": 0,
                    "total_event_types": 0,
                    "min_sessions_threshold": min_sessions,
                },
                "positive_correlations": [],
                "negative_correlations": [],
                "neutral_events": [],
            }

        # Get total sessions and event types from first row (same for all)
        total_sessions = rows[0][5] if rows else 0
        total_converters = rows[0][6] if rows else 0
        total_event_types = rows[0][7] if rows and len(rows[0]) > 7 else 0
        non_converting_sessions_count = total_sessions - total_converters
        baseline_conversion_rate = total_converters / total_sessions if total_sessions > 0 else 0.0

        # Calculate filtered events count
        events_analyzed = len(rows)
        events_filtered_out = max(0, total_event_types - events_analyzed)

        # Process results
        positive_correlations = []
        negative_correlations = []
        neutral_events = []

        # Threshold for neutral: lift between -10% and +10%
        # Higher threshold shows only strong correlations, reducing noise
        NEUTRAL_THRESHOLD = 10.0

        for row in rows:
            event_name = row[0]
            sessions_with_count = row[1]
            sessions_without_count = row[2]
            converters_with = row[3]
            converters_without = row[4]

            # Calculate conversion rates
            rate_with = converters_with / sessions_with_count if sessions_with_count > 0 else 0
            rate_without = (
                converters_without / sessions_without_count if sessions_without_count > 0 else 0
            )

            # Calculate lift (avoid division by zero)
            if rate_without > 0:
                lift_percent = (rate_with / rate_without - 1) * 100
            elif rate_with > 0:
                # If rate_without is 0 but rate_with > 0, that's infinite positive lift
                # Cap it at a high value for display
                lift_percent = 999.9
            else:
                # Both are 0, no correlation
                lift_percent = 0.0

            event_data = {
                "event": event_name,
                "lift_percent": round(lift_percent, 1),
                "sessions_with_event": sessions_with_count,
                "sessions_without_event": sessions_without_count,
                "conversion_rate_with": round(rate_with, 4),
                "conversion_rate_without": round(rate_without, 4),
                "converts_with": converters_with,
                "converts_without": converters_without,
            }

            if lift_percent > NEUTRAL_THRESHOLD:
                positive_correlations.append(event_data)
            elif lift_percent < -NEUTRAL_THRESHOLD:
                negative_correlations.append(event_data)
            else:
                neutral_events.append(event_name)

        # Sort by absolute lift (highest first) and add ranks
        positive_correlations.sort(key=lambda x: x["lift_percent"], reverse=True)
        negative_correlations.sort(key=lambda x: x["lift_percent"])  # Most negative first

        for rank, item in enumerate(positive_correlations[:limit], 1):
            item["rank"] = rank

        for rank, item in enumerate(negative_correlations[:limit], 1):
            item["rank"] = rank

        return {
            "data_quality": {
                "total_sessions": total_sessions,
                "converting_sessions": total_converters,
                "non_converting_sessions": non_converting_sessions_count,
                "baseline_conversion_rate": round(baseline_conversion_rate, 4),
                "events_analyzed": events_analyzed,
                "events_filtered_out": events_filtered_out,
                "total_event_types": total_event_types,
                "min_sessions_threshold": min_sessions,
            },
            "positive_correlations": positive_correlations[:limit],
            "negative_correlations": negative_correlations[:limit],
            "neutral_events": sorted(neutral_events)[:limit],
        }


# NOTE: ConversionSignalsView was removed in v2.0.0
# This view required cross-session user tracking which is not compatible
# with session-based analytics. Use EventCorrelationView for similar insights.


class SegmentComparisonView(APIView):
    """
    API endpoint for comparing conversion rates across different session segments.

    This endpoint provides basic segmentation for comparing conversion rates
    across different groups with flexible time granularity. Segments can
    be based on platform (iOS, Android, Web), country, session depth, or hour of day.

    **Session-Based Analysis:** All analysis is session-scoped. Each unique
    session_id is counted once per period. This provides privacy-friendly
    analytics without cross-session tracking.

    Privacy Note: All segmentation is done on aggregate data only. No individual
    user journeys are exposed. Country data uses ISO country codes from headers
    only - no IP-based geolocation.

    Query Parameters:
        conversion_events (required): Comma-separated list of event names to
            count as conversions (e.g., "purchase,subscription_start")
        segment_by (optional): How to segment data: 'platform' (default), 'country', 'depth',
            'hour', or 'property:<name>' for a property the app declared (respectlytics.com,
            on paid plans), where a value seen in fewer than 5 sessions joins "Other values"
        granularity (optional): Time period grouping - 'day' (default), 'week',
            'month', 'quarter', 'year'
        from (optional): Start date in YYYY-MM-DD format
        to (optional): End date in YYYY-MM-DD format

    Segment Types:
        - platform: iOS, Android, Web, Other (from Event.platform field)
        - country: ISO 2-letter country codes (from Event.country field)
        - depth: Session depth buckets (1, 2, 3, 4, 5, 6-10, 11-20, 21+) based on events per session
        - hour: Hour of day (0-23 UTC) when sessions started - for identifying peak times

    Returns:
        200 OK: Segment comparison with conversion rates per segment per period
        400 Bad Request: If conversion_events missing or invalid parameters
        401 Unauthorized: If app_key missing or invalid

    Response Structure:
        {
            "app_name": str,
            "granularity": str,
            "segment_by": str,
            "conversion_events": [str],
            "date_range": {"from": str, "to": str},
            "summary": {
                "total_segments": int,
                "total_conversions": int,
                "overall_conversion_rate": float
            },
            "segments": [
                {
                    "segment": str,
                    "summary": {
                        "total_active_sessions": int,
                        "total_conversions": int,
                        "conversion_rate": float
                    },
                    "periods": [
                        {
                            "period": str,
                            "active_sessions": int,
                            "conversions": int,
                            "conversion_rate": float
                        }
                    ]
                }
            ]
        }
    """

    share_links = True  # a share link's dashboard reads it (teams/)
    authentication_classes = APP_OWNER
    permission_classes = [HasValidAppKey]

    VALID_GRANULARITIES = ("day", "week", "month", "quarter", "year")
    VALID_SEGMENT_TYPES = ("platform", "country", "depth", "hour")

    @swagger_auto_schema(
        operation_summary="Segment Comparison",
        operation_description="""
Compare conversion rates across different session segments with flexible time granularity.

**Session-Based Analysis:**
All analysis is session-scoped. Each unique session_id is counted once per period.
This provides privacy-friendly analytics without cross-session tracking.

**Segment Types:**
- `platform`: Compare iOS, Android, Web, and Other platforms
- `country`: Compare by ISO 2-letter country code (US, GB, DE, etc.)
- `depth`: Compare by session depth (events per session) - buckets: 1, 2, 3, 4, 5, 6-10, 11-20, 21+
- `hour`: Compare by hour of day (0-23 UTC) - ideal for identifying peak engagement times

**Granularity Options:**
- `day` (default): Daily segment data
- `week`: Weekly segment data - ISO weeks, Mon-Sun
- `month`: Monthly segment data
- `quarter`: Quarterly segment data
- `year`: Yearly segment data

**Period Labels:**
| Granularity | Format | Example |
|-------------|--------|---------|
| day | YYYY-MM-DD | 2025-11-27 |
| week | YYYY-Www | 2025-W48 |
| month | YYYY-MM | 2025-11 |
| quarter | YYYY-Qn | 2025-Q4 |
| year | YYYY | 2025 |

**Privacy Note:**
All segmentation is done on aggregate data only. No individual user journeys
are exposed. Country data comes from request headers only - no IP geolocation.
        """,
        manual_parameters=[
            openapi.Parameter(
                "X-App-Key",
                openapi.IN_HEADER,
                description="App Key for authentication",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "conversion_events",
                openapi.IN_QUERY,
                description=(
                    "REQUIRED: Comma-separated event names to count as conversions (e.g., "
                    "purchase,subscription_complete)"
                ),
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "segment_by",
                openapi.IN_QUERY,
                description=(
                    "Segmentation type: platform (default), country, depth (events per session), "
                    "hour (0-23 UTC), or property:<name> for a declared property "
                    "(respectlytics.com, paid plans)"
                ),
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "granularity",
                openapi.IN_QUERY,
                description="Time period grouping: day (default), week, month, quarter, year",
                type=openapi.TYPE_STRING,
                enum=["day", "week", "month", "quarter", "year"],
                required=False,
            ),
            openapi.Parameter(
                "from",
                openapi.IN_QUERY,
                description="Start date in YYYY-MM-DD format",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "to",
                openapi.IN_QUERY,
                description="End date in YYYY-MM-DD format",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "tz",
                openapi.IN_QUERY,
                description=(
                    "IANA timezone name (e.g., 'America/New_York', 'Europe/London'). Dates are "
                    "interpreted in this timezone. Defaults to UTC."
                ),
                type=openapi.TYPE_STRING,
                required=False,
                default="UTC",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Segment comparison data",
                examples={
                    "application/json": {
                        "app_name": "My App",
                        "granularity": "month",
                        "segment_by": "platform",
                        "conversion_events": ["purchase"],
                        "date_range": {"from": "2025-09-01", "to": "2025-11-27"},
                        "summary": {
                            "total_segments": 2,
                            "total_conversions": 570,
                            "total_sessions": 8027,
                            "overall_conversion_rate": 0.068,
                        },
                        "interpretation": (
                            "Session-scoped analysis: each unique session_id counted once per "
                            "period"
                        ),
                        "segments": [
                            {
                                "segment": "iOS",
                                "summary": {
                                    "total_active_sessions": 4497,
                                    "total_conversions": 359,
                                    "conversion_rate": 0.080,
                                },
                                "periods": [
                                    {
                                        "period": "2025-11",
                                        "active_sessions": 2341,
                                        "conversions": 187,
                                        "conversion_rate": 0.080,
                                    },
                                    {
                                        "period": "2025-10",
                                        "active_sessions": 2156,
                                        "conversions": 172,
                                        "conversion_rate": 0.080,
                                    },
                                ],
                            },
                            {
                                "segment": "Android",
                                "summary": {
                                    "total_active_sessions": 3530,
                                    "total_conversions": 211,
                                    "conversion_rate": 0.060,
                                },
                                "periods": [
                                    {
                                        "period": "2025-11",
                                        "active_sessions": 1876,
                                        "conversions": 112,
                                        "conversion_rate": 0.060,
                                    },
                                    {
                                        "period": "2025-10",
                                        "active_sessions": 1654,
                                        "conversions": 99,
                                        "conversion_rate": 0.060,
                                    },
                                ],
                            },
                        ],
                    }
                },
            ),
            400: openapi.Response(
                description="Bad Request - missing conversion_events or invalid parameters",
                examples={
                    "application/json": {
                        "error": "conversion_events parameter required",
                        "detail": "Please specify which events to count as conversions.",
                        "your_event_types": [
                            "app_open",
                            "screen_view",
                            "button_click",
                            "checkout_start",
                            "payment_success",
                        ],
                        "example": "?conversion_events=payment_success,checkout_start",
                    }
                },
            ),
            401: "Unauthorized - missing or invalid app_key",
        },
    )
    def get(self, request):
        # Get the authenticated app
        app = request.user

        # Parse query parameters
        conversion_events_str = request.query_params.get("conversion_events")
        segment_by = request.query_params.get("segment_by", "platform").lower()
        granularity = request.query_params.get("granularity", "day").lower()
        from_date_str = request.query_params.get("from")
        to_date_str = request.query_params.get("to")

        # Validate conversion_events parameter (REQUIRED)
        if not conversion_events_str:
            # Get user's actual event types to help them
            event_types = list(
                Event.objects.filter(app=app)
                .values_list("event_name", flat=True)
                .distinct()
                .order_by("event_name")[:20]
            )
            return Response(
                {
                    "error": "conversion_events parameter required",
                    "detail": "Please specify which events to count as conversions.",
                    "your_event_types": event_types,
                    "example": "?conversion_events="
                    + (
                        ",".join(event_types[:2])
                        if len(event_types) >= 2
                        else "purchase,subscription"
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse conversion events (comma-separated, trimmed)
        conversion_events = [e.strip() for e in conversion_events_str.split(",") if e.strip()]

        if not conversion_events:
            return Response(
                {
                    "error": "conversion_events parameter is empty",
                    "detail": "Please specify at least one event name.",
                    "example": "?conversion_events=purchase,subscription",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate segment_by: a fixed kind, or a declared property ("property:plan")
        prop = segment_by.split(":", 1)[1] if segment_by.startswith("property:") else None
        if prop is not None and not PROPERTY_NAME.match(prop):
            return Response(
                {"error": "Invalid property name in segment_by"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if prop is not None and not _properties_included(app):
            return Response(
                {"error": "Properties come with every paid plan."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if prop is None and segment_by not in self.VALID_SEGMENT_TYPES:
            return Response(
                {
                    "error": (
                        f"Invalid segment_by. Must be one of: {', '.join(self.VALID_SEGMENT_TYPES)}"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate granularity
        if granularity not in self.VALID_GRANULARITIES:
            return Response(
                {
                    "error": (
                        "Invalid granularity. Must be one of: "
                        f"{', '.join(self.VALID_GRANULARITIES)}"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get timezone parameter
        tz_name = request.query_params.get("tz", "UTC")

        # Start with events for this app
        events = Event.objects.filter(app=app)

        # Parse and apply date filters with timezone awareness
        try:
            from_datetime, to_datetime = parse_date_range(from_date_str, to_date_str, tz_name)
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Default range: the last 30 days, from the reader's midnight (analytics/date_utils.py)
        from_datetime, to_datetime = default_range(from_datetime, to_datetime, tz_name)
        events = events.filter(timestamp__gte=from_datetime, timestamp__lte=to_datetime)

        # PERF-016: Check cache before running expensive analysis
        import hashlib

        from django.conf import settings
        from django.core.cache import cache

        # Use actual date strings for cache key
        cache_from = from_datetime.strftime("%Y-%m-%d") if from_datetime else None
        cache_to = to_datetime.strftime("%Y-%m-%d") if to_datetime else None
        cache_params = (
            f"{','.join(sorted(conversion_events))}:{segment_by}:{granularity}:"
            f"{cache_from}:{cache_to}:{tz_name}"
        )
        cache_hash = hashlib.md5(cache_params.encode()).hexdigest()[:16]
        cache_key = f"segment_comparison:{app.id}:{cache_hash}"

        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return Response(cached_result, status=status.HTTP_200_OK)

        # Choose truncation function based on granularity
        trunc_functions = {
            "day": TruncDay,
            "week": TruncWeek,
            "month": TruncMonth,
            "quarter": TruncQuarter,
            "year": TruncYear,
        }
        # The reader's own periods, as in DAUView
        zone = _get_timezone_safe(tz_name)
        trunc_func = partial(trunc_functions[granularity], tzinfo=zone)

        # Calculate segment data based on segment_by type
        if prop is not None:
            # A declared property's values (properties/, respectlytics.com)
            segments_data = self._calculate_property_segments(
                events, conversion_events, trunc_func, prop
            )
        elif segment_by == "depth":
            # Session depth segmentation (events per session)
            segments_data = self._calculate_depth_segments(
                app.id, from_datetime, to_datetime, conversion_events, granularity, zone
            )
        elif segment_by == "hour":
            # Hourly session patterns (hour of day 0-23)
            segments_data = self._calculate_hourly_segments(
                app.id, from_datetime, to_datetime, conversion_events
            )
        else:
            # Field-based segmentation (platform, country)
            segment_field = "platform" if segment_by == "platform" else "country"
            segments_data = self._calculate_field_segments(
                slices_in(app, from_datetime, to_datetime),
                conversion_events,
                trunc_func,
                segment_field,
            )

        # Format response
        date_range = {
            "from": from_datetime.strftime("%Y-%m-%d") if from_datetime else None,
            "to": to_datetime.strftime("%Y-%m-%d") if to_datetime else None,
        }

        # Calculate overall summary
        total_conversions = sum(s["summary"]["total_conversions"] for s in segments_data)
        total_sessions = sum(s["summary"]["total_active_sessions"] for s in segments_data)
        overall_rate = round(total_conversions / total_sessions, 4) if total_sessions > 0 else 0.0

        # Format periods
        for segment in segments_data:
            segment["periods"] = [
                {
                    "period": self._format_period_label(p["period"], granularity),
                    "active_sessions": p["active_sessions"],
                    "conversions": p["conversions"],
                    "conversion_rate": p["conversion_rate"],
                }
                for p in segment["periods"]
            ]

        response_data = {
            "app_name": app.name,
            "granularity": granularity,
            "segment_by": segment_by,
            "conversion_events": conversion_events,
            "date_range": date_range,
            "summary": {
                "total_segments": len(segments_data),
                "total_conversions": total_conversions,
                "total_sessions": total_sessions,
                "overall_conversion_rate": overall_rate,
            },
            "interpretation": (
                "Session-scoped analysis: each unique session_id counted once per period"
            ),
            "segments": segments_data,
        }

        # PERF-016: Cache the result (3 min TTL)
        cache.set(cache_key, response_data, timeout=settings.CACHE_TTL_CONVERSION)

        return Response(response_data, status=status.HTTP_200_OK)

    def _calculate_field_segments(self, slices, conversion_events, trunc_func, segment_field):
        """
        Calculate segment data for a regular field (platform, country) using session_id.

        PERF-020: Optimized to use single SQL query with CASE expression instead of
        two separate queries + Python merge loop.

        Session-based analysis: Each unique session_id is counted once per period.

        Returns list of segment dicts with summary and periods.
        """
        from django.db.models import Q

        # The range's session slices with a session (analytics.SessionSlice)
        with_session = slices.filter(session_id__isnull=False).exclude(session_id="")

        # One query for both: the sessions, and the sessions with a conversion event, so the
        # rate is sessions over sessions, as for depth and hour (until 2026-10-24 conversions
        # counted the events, and a rate could pass 100%)
        segment_data = [
            {**row, "unique_sessions": row["sessions"], "conversions": row["converting"]}
            for row in sessions_per(
                with_session.annotate(period=trunc_func("quarter")),
                ["period", segment_field],
                converted=Q(names__overlap=list(conversion_events)),
            )
        ]

        return self._segments_from(segment_data, segment_field)

    def _segments_from(self, segment_data, key, label=lambda value: value or "Unknown"):
        """Rows of (period, key, unique_sessions, conversions) as the segments' answer."""
        # Build segment data structure from single query result
        segment_periods = defaultdict(
            lambda: defaultdict(lambda: {"active_sessions": 0, "conversions": 0})
        )

        for item in segment_data:
            segment = label(item[key])
            period = item["period"]
            if period:
                segment_periods[segment][period]["active_sessions"] = item["unique_sessions"]
                segment_periods[segment][period]["conversions"] = item["conversions"]

        # Build response segments
        segments = []
        for segment_name in sorted(segment_periods.keys()):
            periods = segment_periods[segment_name]

            # Sort periods by date (descending)
            sorted_periods = sorted(periods.items(), key=lambda x: x[0], reverse=True)

            # Calculate segment summary
            total_sessions = sum(p["active_sessions"] for p in periods.values())
            total_conversions = sum(p["conversions"] for p in periods.values())
            segment_rate = (
                round(total_conversions / total_sessions, 4) if total_sessions > 0 else 0.0
            )

            period_list = []
            for period_dt, period_data in sorted_periods:
                sessions = period_data["active_sessions"]
                conversions = period_data["conversions"]
                rate = round(conversions / sessions, 4) if sessions > 0 else 0.0
                period_list.append(
                    {
                        "period": period_dt,
                        "active_sessions": sessions,
                        "conversions": conversions,
                        "conversion_rate": rate,
                    }
                )

            segments.append(
                {
                    "segment": segment_name,
                    "summary": {
                        "total_active_sessions": total_sessions,
                        "total_conversions": total_conversions,
                        "conversion_rate": segment_rate,
                    },
                    "periods": period_list,
                }
            )

        # Sort segments by total conversions (descending)
        segments.sort(key=lambda x: x["summary"]["total_conversions"], reverse=True)

        return segments

    def _calculate_property_segments(self, events, conversion_events, trunc_func, name):
        """A declared property's values as segments (properties/, respectlytics.com): for each
        value, the sessions with an event that carried it and those of them with a conversion
        event, sessions over sessions. A value seen in fewer than MIN_PROPERTY_SESSIONS
        sessions joins one "Other values" row, so a rare value never stands alone. Read on the
        (app, timestamp) index, as every segment is."""
        from django.db.models import Q, Subquery
        from django.db.models.fields.json import KeyTextTransform

        with_session = events.filter(session_id__isnull=False).exclude(session_id="")
        converting = with_session.filter(event_name__in=conversion_events).values("session_id")
        rows = [
            {**row, "unique_sessions": row["sessions"], "conversions": row["converting"]}
            for row in sessions_per(
                with_session.filter(properties__has_key=name).annotate(
                    period=trunc_func("timestamp"), value=KeyTextTransform(name, "properties")
                ),
                ["period", "value"],
                converted=Q(session_id__in=Subquery(converting)),
            )
        ]
        totals = defaultdict(int)
        for row in rows:
            totals[row["value"]] += row["unique_sessions"]
        rare = {value for value, n in totals.items() if n < MIN_PROPERTY_SESSIONS}
        if rare:
            merged = defaultdict(lambda: {"unique_sessions": 0, "conversions": 0})
            for row in rows:
                value = OTHER_VALUES if row["value"] in rare else row["value"]
                cell = merged[(row["period"], value)]
                cell["unique_sessions"] += row["unique_sessions"]
                cell["conversions"] += row["conversions"]
            rows = [{"period": p, "value": v, **c} for (p, v), c in merged.items()]
        return self._segments_from(rows, "value")

    def _calculate_depth_segments(
        self, app_id, from_date, to_date, conversion_events, granularity, zone
    ):
        """
        Calculate segment data based on session depth (events per session).

        Session depth buckets: 1, 2, 3, 4, 5, 6-10, 11-20, 21+
        Finer granularity at low end where most sessions fall.

        This uses raw SQL for efficient bucketing with CASE expressions.

        Args:
            app_id: UUID of the app
            from_date: Start datetime for the query
            to_date: End datetime for the query
            conversion_events: List of event names to count as conversions
            granularity: day, week, month, quarter or year
            zone: the reader's time zone, whose periods these are

        Returns list of segment dicts with summary and periods.
        """
        from collections import defaultdict

        from django.db import connection

        # The period in the reader's zone: the unit is one of five known words, never the caller's
        unit = granularity if granularity in ("day", "week", "month", "quarter") else "year"
        trunc_sql = f"DATE_TRUNC('{unit}', MIN(first_at) AT TIME ZONE %s)"

        # The conversion events as one array parameter, never as text in the SQL: a name is
        # whatever the caller sent

        # Build date filter SQL
        date_filter = ""
        params = [zone.key, list(conversion_events), str(app_id)]  # in the order the query asks
        if from_date:
            date_filter += " AND quarter >= %s"
            params.append(from_date)
        if to_date:
            date_filter += " AND quarter <= %s"
            params.append(to_date)

        # SQL query to calculate session depth buckets with conversion rates
        sql = f"""
        WITH session_stats AS (
            SELECT
                session_id COLLATE "C" AS session_id,
                {trunc_sql} as period,
                SUM(events) as event_count,
                MAX(CASE WHEN names && %s::varchar[] THEN 1 ELSE 0 END) as converted
            FROM analytics_sessionslice
            WHERE app_id = %s
                AND session_id IS NOT NULL
                AND session_id != ''
                {date_filter}
            GROUP BY 1
        ),
        depth_buckets AS (
            SELECT
                period,
                CASE
                    WHEN event_count = 1 THEN '1'
                    WHEN event_count = 2 THEN '2'
                    WHEN event_count = 3 THEN '3'
                    WHEN event_count = 4 THEN '4'
                    WHEN event_count = 5 THEN '5'
                    WHEN event_count BETWEEN 6 AND 10 THEN '6-10'
                    WHEN event_count BETWEEN 11 AND 20 THEN '11-20'
                    ELSE '21+'
                END as depth_bucket,
                converted
            FROM session_stats
            WHERE period IS NOT NULL
        )
        SELECT
            depth_bucket,
            period,
            COUNT(*) as session_count,
            SUM(converted) as conversions
        FROM depth_buckets
        GROUP BY depth_bucket, period
        ORDER BY
            CASE depth_bucket
                WHEN '1' THEN 1
                WHEN '2' THEN 2
                WHEN '3' THEN 3
                WHEN '4' THEN 4
                WHEN '5' THEN 5
                WHEN '6-10' THEN 6
                WHEN '11-20' THEN 7
                ELSE 8
            END,
            period DESC;
        """

        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        # Build segment data structure
        segment_periods = defaultdict(
            lambda: defaultdict(lambda: {"active_sessions": 0, "conversions": 0})
        )

        for row in rows:
            depth_bucket, period, session_count, conversions = row
            if period:
                segment_periods[depth_bucket][period]["active_sessions"] = session_count
                segment_periods[depth_bucket][period]["conversions"] = conversions

        # Define bucket order for consistent sorting
        bucket_order = ["1", "2", "3", "4", "5", "6-10", "11-20", "21+"]

        # Build response segments in bucket order (always include all 8 buckets)
        segments = []
        for bucket_name in bucket_order:
            # Get periods for this bucket, or empty dict if no data
            periods = segment_periods.get(bucket_name, {})

            # Sort periods by date (descending)
            sorted_periods = sorted(periods.items(), key=lambda x: x[0], reverse=True)

            # Calculate segment summary
            total_sessions = sum(p["active_sessions"] for p in periods.values())
            total_conversions = sum(p["conversions"] for p in periods.values())
            segment_rate = (
                round(total_conversions / total_sessions, 4) if total_sessions > 0 else 0.0
            )

            period_list = []
            for period_dt, period_data in sorted_periods:
                sessions = period_data["active_sessions"]
                conversions = period_data["conversions"]
                rate = round(conversions / sessions, 4) if sessions > 0 else 0.0
                period_list.append(
                    {
                        "period": period_dt,
                        "active_sessions": sessions,
                        "conversions": conversions,
                        "conversion_rate": rate,
                    }
                )

            segments.append(
                {
                    "segment": bucket_name,
                    "summary": {
                        "total_active_sessions": total_sessions,
                        "total_conversions": total_conversions,
                        "conversion_rate": segment_rate,
                    },
                    "periods": period_list,
                }
            )

        return segments

    def _calculate_hourly_segments(self, app_id, from_date, to_date, conversion_events):
        """
        Calculate segment data based on hour of day (0-23 UTC).

        This analysis helps identify peak engagement times by showing
        when sessions start and their conversion rates by hour.

        Note: The 'granularity' parameter is ignored for hourly segments
        since the analysis is inherently aggregated by hour across all days.

        Args:
            app_id: UUID of the app
            from_date: Start datetime for the query
            to_date: End datetime for the query
            conversion_events: List of event names to count as conversions

        Returns list of 24 segment dicts (hours 0-23), each with summary only (no periods).
        """
        from django.db import connection

        # The conversion events as one array parameter, never as text in the SQL: a name is
        # whatever the caller sent

        # Build date filter SQL
        date_filter = ""
        params = [list(conversion_events), str(app_id)]
        if from_date:
            date_filter += " AND quarter >= %s"
            params.append(from_date)
        if to_date:
            date_filter += " AND quarter <= %s"
            params.append(to_date)

        # SQL query to calculate hourly session patterns
        # Uses EXTRACT(HOUR FROM timestamp AT TIME ZONE 'UTC') for consistent UTC hours
        sql = f"""
        WITH session_hours AS (
            SELECT
                session_id COLLATE "C" AS session_id,
                EXTRACT(HOUR FROM MIN(first_at) AT TIME ZONE 'UTC') as session_hour,
                MAX(CASE WHEN names && %s::varchar[] THEN 1 ELSE 0 END) as converted
            FROM analytics_sessionslice
            WHERE app_id = %s
                AND session_id IS NOT NULL
                AND session_id != ''
                {date_filter}
            GROUP BY 1
        )
        SELECT
            session_hour::int as hour,
            COUNT(*) as session_count,
            SUM(converted) as conversions
        FROM session_hours
        GROUP BY session_hour
        ORDER BY session_hour;
        """

        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        # Build segment data structure with all 24 hours (fill missing with zeros)
        hourly_data = {i: {"session_count": 0, "conversions": 0} for i in range(24)}

        for row in rows:
            hour, session_count, conversions = row
            if hour is not None and 0 <= hour <= 23:
                hourly_data[int(hour)] = {
                    "session_count": session_count,
                    "conversions": conversions or 0,
                }

        # Build response segments in hour order (0-23)
        segments = []
        for hour in range(24):
            data = hourly_data[hour]
            session_count = data["session_count"]
            conversions = data["conversions"]
            rate = round(conversions / session_count, 4) if session_count > 0 else 0.0

            # For hourly segments, we don't have period breakdowns
            # The segment itself IS the breakdown (by hour)
            # So we use a single "period" entry that spans the entire date range
            segments.append(
                {
                    "segment": str(hour),
                    "summary": {
                        "total_active_sessions": session_count,
                        "total_conversions": conversions,
                        "conversion_rate": rate,
                    },
                    "periods": [],  # No time-based periods for hourly analysis
                }
            )

        return segments

    def _format_period_label(self, dt, granularity):
        """
        Format a datetime into the appropriate period label.

        Args:
            dt: datetime object (truncated to period start)
            granularity: one of 'day', 'week', 'month', 'quarter', 'year'

        Returns:
            Formatted string label for the period
        """
        if granularity == "day":
            return dt.strftime("%Y-%m-%d")
        elif granularity == "week":
            # ISO week format: YYYY-Www
            iso_cal = dt.isocalendar()
            return f"{iso_cal[0]}-W{iso_cal[1]:02d}"
        elif granularity == "month":
            return dt.strftime("%Y-%m")
        elif granularity == "quarter":
            quarter = (dt.month - 1) // 3 + 1
            return f"{dt.year}-Q{quarter}"
        elif granularity == "year":
            return str(dt.year)
        return dt.strftime("%Y-%m-%d")


class GlobeStatsView(APIView):
    """
    Optimized API endpoint for globe visualization analytics.

    Returns country-level aggregated statistics optimized for geographic visualization.
    Unlike the segment-comparison API which groups by period × country (expensive),
    this endpoint only groups by country for 10x performance improvement.

    Performance Characteristics:
        - Expected response time: 200-500ms for 500K events
        - Cache TTL: 15 minutes
        - Query optimization: GROUP BY country only (no period grouping)
        - Index used: (app, timestamp, country)

    Query Parameters:
        app_key (required): Application API key
        from (required): Start date (YYYY-MM-DD format)
        to (required): End date (YYYY-MM-DD format)
        conversion_events (optional): Comma-separated list of conversion event names

    Response Format:
        {
            "data": [
                {
                    "country": "US",
                    "events": 1234,
                    "sessions": 567,
                    "conversions": 89,
                    "conversion_rate": 15.7
                },
                ...
            ],
            "cached": true,
            "cache_expires_in": 900
        }
    """

    share_links = True  # a share link's dashboard reads it (teams/)
    authentication_classes = APP_OWNER
    permission_classes = [HasValidAppKey]

    @swagger_auto_schema(
        operation_description="""
        Get country-level analytics optimized for globe visualizations.

        This endpoint provides aggregated statistics by country without period grouping,
        making it significantly faster than segment-comparison for geographic data.
        Results are cached for 15 minutes for optimal performance.
        """,
        manual_parameters=[
            openapi.Parameter(
                "app_key",
                openapi.IN_QUERY,
                description="Your application's API key (required)",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "from",
                openapi.IN_QUERY,
                description="Start date in YYYY-MM-DD format (required)",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
                required=True,
            ),
            openapi.Parameter(
                "to",
                openapi.IN_QUERY,
                description="End date in YYYY-MM-DD format (required)",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
                required=True,
            ),
            openapi.Parameter(
                "tz",
                openapi.IN_QUERY,
                description=(
                    "IANA timezone name (e.g., 'America/New_York', 'Europe/London'). Dates are "
                    "interpreted in this timezone. Defaults to UTC."
                ),
                type=openapi.TYPE_STRING,
                required=False,
                default="UTC",
            ),
            openapi.Parameter(
                "conversion_events",
                openapi.IN_QUERY,
                description=(
                    "Comma-separated list of event names to count as conversions (optional)"
                ),
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Country-level statistics",
                examples={
                    "application/json": {
                        "data": [
                            {
                                "country": "US",
                                "events": 1234,
                                "sessions": 567,
                                "conversions": 89,
                                "conversion_rate": 15.7,
                            },
                            {
                                "country": "GB",
                                "events": 890,
                                "sessions": 345,
                                "conversions": 45,
                                "conversion_rate": 13.0,
                            },
                        ],
                        "cached": True,
                        "cache_expires_in": 900,
                    }
                },
            ),
            400: "Bad request - missing or invalid parameters",
            401: "Unauthorized - invalid or missing API key",
            500: "Internal server error",
        },
    )
    def get(self, request):
        """
        Handle GET request for globe statistics.

        Returns aggregated analytics by country with optional conversion metrics.
        Implements 15-minute caching and performance monitoring.
        """
        import time

        from django.conf import settings
        from django.core.cache import cache
        from django.db import connection
        from django.db.models import Q

        logger = logging.getLogger("analytics.performance")
        start_time = time.time()

        try:
            # Extract and validate parameters
            app_key = request.GET.get("app_key")
            from_date_str = request.GET.get("from")
            to_date_str = request.GET.get("to")
            conversion_events_str = request.GET.get("conversion_events", "")
            tz_name = request.GET.get("tz", "UTC")

            # Validate required parameters
            if not all([app_key, from_date_str, to_date_str]):
                return Response(
                    {"error": "Missing required parameters: app_key, from, to"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Parse dates with timezone awareness
            try:
                from_datetime, to_datetime = parse_date_range(from_date_str, to_date_str, tz_name)
                # Extract date parts for validation and later use
                from_date = from_datetime.date() if from_datetime else None
                to_date = to_datetime.date() if to_datetime else None
            except ValueError:
                return Response(
                    {"error": "Invalid date format. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validate date range
            if from_date and to_date and from_date > to_date:
                return Response(
                    {"error": "from date must be before or equal to to date"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Parse conversion events
            conversion_events = []
            if conversion_events_str:
                conversion_events = [
                    e.strip() for e in conversion_events_str.split(",") if e.strip()
                ]

            # Build cache key
            import hashlib

            conversion_hash = hashlib.md5(",".join(sorted(conversion_events)).encode()).hexdigest()[
                :8
            ]
            fresh = freshness_mark(
                app_key, to_date_str, getattr(settings, "GLOBE_STATS_CACHE_TTL", 900)
            )
            cache_key = (
                f"globe_stats_{app_key}_{conversion_hash}_{from_date_str}_{to_date_str}"
                f"_{_get_timezone_safe(tz_name).key}"
                f"_{fresh}"
            )

            # Check cache
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                total_duration = time.time() - start_time
                logger.info(
                    f"globe-stats cache hit: {total_duration * 1000:.0f}ms | "
                    f"app_key={app_key} | from={from_date_str} | to={to_date_str}"
                )
                cache_ttl = getattr(settings, "GLOBE_STATS_CACHE_TTL", 900)
                return Response(
                    {"data": cached_data, "cached": True, "cache_expires_in": cache_ttl}
                )

            # Get app from request (set by AppOwnerSessionAuthentication as request.user)
            app = request.user

            # Set query timeout from settings
            query_timeout = (
                getattr(settings, "GLOBE_STATS_QUERY_TIMEOUT", 30) * 1000
            )  # Convert to milliseconds
            with connection.cursor() as cursor:
                cursor.execute(f"SET statement_timeout = {query_timeout}")

            # The range's session slices with a country (analytics.SessionSlice)
            queryset = slices_in(app, from_datetime, to_datetime).filter(country__isnull=False)

            # Execute optimized query: GROUP BY country only (no period grouping)
            query_start = time.time()

            # Sessions with a conversion event, so the rate is sessions over sessions and never
            # passes 100% (until 2026-10-24 it counted the events); sessions grouped by hash
            # first (analytics/base_events.py)
            results = [
                {**row, "conversions": row.get("converting", 0)}
                for row in sessions_per(
                    queryset,
                    ["country"],
                    converted=Q(names__overlap=list(conversion_events))
                    if conversion_events
                    else None,
                    order="3 DESC",  # most events first
                )
            ]

            query_duration = time.time() - query_start

            # Log slow queries using threshold from settings
            slow_query_threshold = getattr(settings, "GLOBE_STATS_SLOW_QUERY_THRESHOLD", 2)
            if query_duration > slow_query_threshold:
                logger.warning(
                    f"Slow globe-stats query: {query_duration:.2f}s | "
                    f"app_key={app_key} | from={from_date_str} | to={to_date_str} | "
                    f"result_count={len(results)}"
                )

            # Calculate conversion rates in Python (fast operation)
            enhanced_results = []
            for item in results:
                country_data = {
                    "country": item["country"],
                    "events": item["events"],
                    "sessions": item["sessions"],
                }

                # Add conversion metrics if available
                if conversion_events:
                    conversions = item.get("conversions", 0)
                    country_data["conversions"] = conversions
                    country_data["conversion_rate"] = round(
                        (conversions / item["sessions"] * 100) if item["sessions"] > 0 else 0, 2
                    )
                else:
                    country_data["conversions"] = 0
                    country_data["conversion_rate"] = 0

                enhanced_results.append(country_data)

            # Cache with TTL from settings
            cache_ttl = getattr(settings, "GLOBE_STATS_CACHE_TTL", 900)
            cache.set(cache_key, enhanced_results, cache_ttl)

            # Calculate total response time
            total_duration = time.time() - start_time

            # Log performance metrics
            logger.info(
                f"globe-stats completed: {total_duration * 1000:.0f}ms | "
                f"query={query_duration * 1000:.0f}ms | "
                f"countries={len(enhanced_results)} | "
                f"cached=False"
            )

            # Build response
            response_data = {
                "data": enhanced_results,
                "cached": False,
                "cache_expires_in": cache_ttl,
            }

            # Add debug info in DEBUG mode
            if getattr(settings, "DEBUG", False):
                response_data["_debug"] = {
                    "query_time_ms": int(query_duration * 1000),
                    "total_time_ms": int(total_duration * 1000),
                    "result_count": len(enhanced_results),
                    "conversion_events": conversion_events,
                }

            return Response(response_data)

        except Exception as e:
            logger.error(
                f"globe-stats error: {str(e)} | "
                f"app_key={request.GET.get('app_key')} | "
                f"from={request.GET.get('from')} | to={request.GET.get('to')}",
                exc_info=True,
            )

            error_detail = str(e) if getattr(settings, "DEBUG", False) else "Internal server error"
            return Response(
                {"error": "Failed to fetch globe statistics", "detail": error_detail},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        finally:
            # The time limit set above holds for this connection, which Django keeps for the next
            # request (CONN_MAX_AGE), whatever that request is: give the server's default back.
            try:
                with connection.cursor() as cursor:
                    cursor.execute("RESET statement_timeout")
            except Exception:
                logger.warning("globe-stats: could not reset the statement timeout")

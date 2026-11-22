"""The nightly comparison of the session slices with the events (analytics.SessionSlice).

Triggers keep the slices in the same transaction as every write of events (migration 0023), so
they are exact. Two writes that race, a deletion counting a quarter again while an event is still
being added to it, can leave one slice behind, and so can anything that ever bypasses the
triggers. daily_jobs compares the last two days, slice by slice, with the events, counts again
every quarter that differs, and logs how many there were, which is normally none.
"""

import logging
from datetime import timedelta

from django.db import connection
from django.utils import timezone

logger = logging.getLogger(__name__)

QUARTER = "date_bin('15 minutes', \"timestamp\", TIMESTAMPTZ '2000-01-01 00:00:00+00')"

DIFFERENT = f"""
WITH expected AS (
    SELECT app_id, session_id, {QUARTER} AS quarter, platform, country,
        MIN("timestamp") AS first_at, MAX("timestamp") AS last_at, COUNT(*) AS events,
        array_agg(DISTINCT event_name ORDER BY event_name) AS names,
        (array_agg(event_name ORDER BY "timestamp" DESC, event_name DESC))[1] AS last_name
    FROM analytics_event
    WHERE "timestamp" >= %(since)s AND "timestamp" < %(until)s
    GROUP BY 1, 2, 3, 4, 5
),
stored AS (
    SELECT app_id, session_id, quarter, platform, country, first_at, last_at,
        events::bigint, names, last_name
    FROM analytics_sessionslice
    WHERE quarter >= %(since)s AND quarter < %(until)s
),
different AS (
    (SELECT * FROM expected EXCEPT SELECT * FROM stored)
    UNION
    (SELECT * FROM stored EXCEPT SELECT * FROM expected)
)
SELECT DISTINCT app_id, quarter FROM different
"""


def compare(days: int = 2) -> int:
    """Count again every quarter of the last `days` UTC days whose slices differ from the
    events, up to the quarter now running; the number of quarters counted again."""
    now = timezone.now()
    until = now.replace(minute=now.minute - now.minute % 15, second=0, microsecond=0)
    since = until.replace(hour=0, minute=0) - timedelta(days=days - 1)
    with connection.cursor() as cursor:
        cursor.execute(DIFFERENT, {"since": since, "until": until})
        stale = cursor.fetchall()
        if stale:
            cursor.execute(
                "SELECT analytics_session_slices_recount(%s::uuid[], %s::timestamptz[])",
                [[str(app) for app, _ in stale], [quarter for _, quarter in stale]],
            )
    if stale:
        logger.warning(
            "[SLICES] %s quarters differed from the events and were counted again", len(stale)
        )
    return len(stale)


def compare_job():
    """Scheduler entry point."""
    logger.info("[SLICES] compared, %s quarters counted again", compare())

"""The summary's figures for a range, in two passes over the app's events (CLAUDE.md, Database
work is the cheapest that answers).

Until 2026-10-26 the summary read the range five times: the total, the names, the days with
their sessions, the top countries and how many countries; the days' distinct sessions were
sorted on disk. Now one pass counts the events by name and by country (grouping sets), and each
day's events and sessions come from the session slices, a row or two per session.
"""

from django.db import connection
from django.db.models.functions import TruncDate

from .base_events import sessions_per
from .date_utils import _get_timezone_safe


def summary_figures(events, slices, tz_name) -> dict:
    """total_events, events_by_name, events_by_day, top_countries and unique_countries of
    `events` (the app's events in the range), its days and their sessions read from `slices`
    (the same range's session slices, analytics.SessionSlice), counted in `tz_name`."""
    base_sql, base_params = (
        events.order_by().values("event_name", "country", "timestamp", "session_id").query
    ).sql_with_params()
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT GROUPING(event_name) AS by_country, event_name, country, COUNT(*)
            FROM ({base_sql}) e
            GROUP BY GROUPING SETS ((event_name), (country))
            """,
            base_params,
        )
        grouped = cursor.fetchall()

    days = sessions_per(
        slices.annotate(day=TruncDate("quarter", tzinfo=_get_timezone_safe(tz_name))),
        ["day"],
        order='"day"',
    )
    events_by_name = {name: count for by_country, name, _, count in grouped if not by_country}
    countries = sorted(
        ((country, count) for by_country, _, country, count in grouped if by_country and country),
        key=lambda pair: (-pair[1], pair[0]),
    )
    return {
        "total_events": sum(events_by_name.values()),
        "events_by_name": events_by_name,
        "events_by_day": [
            {
                "date": d["day"].strftime("%Y-%m-%d"),
                "count": d["events"],
                "unique_buckets": d["sessions"],
            }
            for d in days
        ],
        "top_countries": [{"country": c, "count": n} for c, n in countries[:10]],
        "unique_countries": len(countries),
    }

"""The countries and platforms an app's events carry, for the dashboard's filters, read by index
probes and never by a read of the app's events (CLAUDE.md, Database work is the cheapest that
answers).

Until 2026-10-26 the filter options aggregated every event the app had ever sent, almost five
seconds on six million events. The (app, country, platform) index is walked one pair at a time,
each probe starting after the last pair found, so the cost is one short index read per pair the
app has sent, as known_names does for event names (analytics/event_groups.py).
"""

from django.db import connection

MAX_PAIRS = 5000  # far above what the fixed country and platform lists allow


def countries_and_platforms(app_id) -> tuple[list[str], list[str]]:
    """Every country and every platform the app's events carry, each list sorted."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH RECURSIVE pairs(country, platform, n) AS (
                (SELECT country, platform, 1 FROM analytics_event
                 WHERE app_id = %s AND country IS NOT NULL
                 ORDER BY country, platform LIMIT 1)
                UNION ALL
                SELECT next.country, next.platform, pairs.n + 1
                FROM pairs, LATERAL (
                    SELECT country, platform FROM analytics_event
                    WHERE app_id = %s AND (country, platform) > (pairs.country, pairs.platform)
                    ORDER BY country, platform LIMIT 1
                ) next
                WHERE pairs.n < %s
            ),
            -- Platforms of events with no country, which the pairs above never reach
            countryless(platform, n) AS (
                (SELECT platform, 1 FROM analytics_event
                 WHERE app_id = %s AND country IS NULL AND platform IS NOT NULL
                 ORDER BY platform LIMIT 1)
                UNION ALL
                SELECT next.platform, countryless.n + 1
                FROM countryless, LATERAL (
                    SELECT platform FROM analytics_event
                    WHERE app_id = %s AND country IS NULL AND platform > countryless.platform
                    ORDER BY platform LIMIT 1
                ) next
                WHERE countryless.n < %s
            )
            SELECT country, platform FROM pairs
            UNION ALL
            SELECT NULL, platform FROM countryless
            """,
            [app_id, app_id, MAX_PAIRS, app_id, app_id, MAX_PAIRS],
        )
        rows = cursor.fetchall()

    def cleaned(values):
        return sorted({v.strip() for v in values if v and v.strip()})

    return cleaned(c for c, _ in rows), cleaned(p for _, p in rows)

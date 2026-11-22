"""The events a raw analytics query starts from, as SQL (CLAUDE.md, Database work is the
cheapest that answers).

The conversion views and the funnel build their SQL on a queryset's own (`WITH base_events AS
(...)`). Taken as it is, that SQL selects every column of every event and orders them by the
model's `-timestamp`, so Postgres walked the timestamp index of all apps backwards and a CTE read
more than once was written to disk with every column, the JSON properties included (2026-10-26,
measured on six million events: most of a drop-off's twelve seconds). Here it is the three
columns those queries read, in no order, so the app's own indexes carry it and what is kept
between steps is narrow.
"""

from datetime import UTC

from django.db import connection


def base_events(events):
    """`events` as SQL and parameters for a WITH clause: session_id, event_name and timestamp."""
    return events.order_by().values("session_id", "event_name", "timestamp").query.sql_with_params()


def sessions_per(events, keys, converted=None, order=""):
    """Sessions per `keys` (columns `events` is annotated with), as dicts of the keys with
    `sessions`, `events` and, given `converted` (a Q over the events), `converting`: the
    sessions with at least one event it matches.

    COUNT(DISTINCT session_id) per period sorts every session id of the range, on disk once the
    range is large (1.7 s of DAU's 2.4 s on two million events); each (keys, session) is grouped
    by hash first here, then counted, session ids compared byte for byte (COLLATE "C"), which
    is what equality means for them and several times faster to sort than the locale's order.
    Events without a session count as events and never as a session, as COUNT(DISTINCT
    session_id) counted them."""
    from django.db.models import Count, Sum
    from django.db.models.functions import Collate

    from .models import SessionSlice

    # Read from events, each row is one event; from session slices, a row holds `events` of them
    n = Sum("events") if events.model is SessionSlice else Count("pk")
    inner = (
        events.order_by()
        .annotate(sid=Collate("session_id", "C"))
        .values(*keys, "sid")
        .annotate(n=n)
    )
    if converted is not None:
        inner = inner.annotate(c=Count("pk", filter=converted))
    sql, params = inner.query.sql_with_params()
    columns = ", ".join(f'"{key}"' for key in keys)
    converting = ", COUNT(sid) FILTER (WHERE c > 0)" if converted is not None else ""
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {columns}, COUNT(sid), SUM(n){converting} FROM ({sql}) s "
            f"GROUP BY {columns}{' ORDER BY ' + order if order else ''}",
            params,
        )
        rows = cursor.fetchall()
    # A key that is an annotation (a period, made aware in its zone) is read back as Django
    # reads it
    converters = {}
    for i, key in enumerate(keys):
        expression = inner.query.annotations.get(key)
        if expression is not None:
            converters[i] = (
                expression,
                connection.ops.get_db_converters(expression)
                + expression.get_db_converters(connection),
            )
    names = [*keys, "sessions", "events"] + (["converting"] if converted is not None else [])
    answer = []
    for row in rows:
        row = list(row)
        for i, (expression, functions) in converters.items():
            for function in functions:
                row[i] = function(row[i], expression, connection)
        answer.append(dict(zip(names, row, strict=True)))
    return answer


def slices_in(app, start=None, end=None):
    """The app's session slices (analytics.SessionSlice) whose quarter hours lie in [start, end].

    Every range a view reads begins on a whole quarter hour (the reader's midnight, by
    parse_date_range and default_range), so these slices hold exactly the range's events. A
    start between two quarters, which no view sends, is taken from the start of its quarter."""
    from .models import SessionSlice

    slices = SessionSlice.objects.filter(app=app)
    if start is not None:
        start = start.astimezone(UTC)
        start = start.replace(minute=start.minute - start.minute % 15, second=0, microsecond=0)
        slices = slices.filter(quarter__gte=start)
    if end is not None:
        slices = slices.filter(quarter__lte=end)
    return slices


def session_count(slices) -> int:
    """How many sessions the slices hold, events without a session counted as one, as
    `values("session_id").distinct().count()` over the events counted them; by hash."""
    from django.db.models import Sum
    from django.db.models.functions import Collate

    return (
        slices.order_by()
        .annotate(sid=Collate("session_id", "C"))
        .values("sid")
        .annotate(n=Sum("events"))
        .count()
    )

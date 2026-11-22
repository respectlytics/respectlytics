"""Counts toward blocks, lockout warnings and limits, in a table of their own (analytics.Counter).

Until 2026-10-26 these counts lived in the database cache, which, once it holds MAX_ENTRIES rows,
deletes the alphabetically lowest third of its keys on the next write; every distinct dashboard
question writes a key, so anyone signed in could wipe the counts that lead to a ban. Here each
count is one row, updated in one statement (no read then write, so two requests cannot both
count from the same number), and nothing but its own window ends it.

Every function fails open like the code before it: a database that cannot answer never takes a
request down with it; the caller decides what that means.
"""

import random

from django.db import connection
from django.utils import timezone

from .models import Counter

# Expired rows are deleted now and then by whoever counts, so the table stays small.
PURGE_CHANCE = 0.01

_HIT = """
INSERT INTO analytics_counter (subject, item, count, expires_at)
VALUES (%s, %s, %s, now() + make_interval(secs => %s))
ON CONFLICT (subject, item) DO UPDATE SET
    count = CASE WHEN analytics_counter.expires_at <= now() THEN EXCLUDED.count
                 ELSE analytics_counter.count + EXCLUDED.count END,
    expires_at = CASE WHEN analytics_counter.expires_at <= now() THEN EXCLUDED.expires_at
                      ELSE analytics_counter.expires_at END
RETURNING count
"""


def hit(subject: str, window: int, item: str = "", amount: int = 1) -> int:
    """Count `amount` more for `subject` and return the count in its window, which starts at the
    first count and lasts `window` seconds."""
    with connection.cursor() as cursor:
        cursor.execute(_HIT, [subject[:120], item[:64], amount, window])
        count = cursor.fetchone()[0]
    if random.random() < PURGE_CHANCE:
        purge()
    return count


def distinct(subject: str, window: int, item: str) -> int:
    """Note `item` for `subject` and return how many different items it has had in the last
    `window` seconds (each item counts for `window` seconds from when it was first seen)."""
    hit(subject, window, item)
    return Counter.objects.filter(subject=subject[:120], expires_at__gt=timezone.now()).count()


def peek(subject: str, item: str = "") -> int:
    """The count for `subject` in its window, without counting."""
    row = (
        Counter.objects.filter(subject=subject[:120], item=item[:64], expires_at__gt=timezone.now())
        .values_list("count", flat=True)
        .first()
    )
    return row or 0


def clear(subject: str) -> None:
    """Start `subject` again from nothing (a block that just fired, a successful sign-in)."""
    Counter.objects.filter(subject=subject[:120]).delete()


def purge(now=None) -> int:
    """Delete every count whose window has ended; returns how many."""
    deleted, _ = Counter.objects.filter(expires_at__lte=now or timezone.now()).delete()
    return deleted

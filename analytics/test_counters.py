"""The counts behind blocks, lockout warnings and limits live in a table of their own
(analytics/counters.py), so nothing done to the cache of answers can wipe them."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from . import counters
from .models import Counter


class CountersTest(TestCase):
    def test_counts_go_up_one_at_a_time_within_the_window(self):
        self.assertEqual([counters.hit("s", 60) for _ in range(3)], [1, 2, 3])
        self.assertEqual(counters.peek("s"), 3)

    def test_a_count_can_weigh_more_than_one(self):
        self.assertEqual(counters.hit("w", 60, amount=10), 10)
        self.assertEqual(counters.hit("w", 60, amount=3), 13)

    def test_a_window_that_ended_starts_again_from_one(self):
        counters.hit("s", 60)
        counters.hit("s", 60)
        Counter.objects.filter(subject="s").update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(counters.peek("s"), 0)
        self.assertEqual(counters.hit("s", 60), 1)

    def test_distinct_counts_each_thing_once(self):
        for page in ("a", "b", "a", "c", "b"):
            seen = counters.distinct("scan", 300, page)
        self.assertEqual(seen, 3)

    def test_clear_and_purge(self):
        counters.hit("s", 60)
        counters.hit("old", 60)
        Counter.objects.filter(subject="old").update(expires_at=timezone.now() - timedelta(days=1))
        self.assertEqual(counters.purge(), 1)
        counters.clear("s")
        self.assertFalse(Counter.objects.exists())

    def test_nothing_done_to_the_cache_touches_them(self):
        counters.hit("failed_auth:x", 900)
        cache.clear()
        self.assertEqual(counters.peek("failed_auth:x"), 1)

    def test_subjects_are_kept_to_their_column_length(self):
        long = "x" * 500
        self.assertEqual(counters.hit(long, 60), 1)
        self.assertEqual(counters.peek(long), 1)

"""The session slices are always exactly what the events give, however events are written,
changed or deleted (analytics.SessionSlice, migration 0023)."""

import random
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from analytics import slices
from analytics.models import App, Event, SessionSlice


def quarter(moment):
    moment = moment.astimezone(UTC)
    return moment.replace(minute=moment.minute - moment.minute % 15, second=0, microsecond=0)


def expected(app):
    """The slices, worked out in Python from the app's events."""
    groups = defaultdict(list)
    for e in Event.objects.filter(app=app):
        groups[(e.session_id, quarter(e.timestamp), e.platform, e.country)].append(e)
    answer = {}
    for key, events in groups.items():
        latest = max(events, key=lambda e: (e.timestamp, e.event_name))
        answer[key] = (
            min(e.timestamp for e in events),
            max(e.timestamp for e in events),
            len(events),
            frozenset(e.event_name for e in events),
            latest.event_name,
        )
    return answer


def stored(app):
    return {
        (s.session_id, s.quarter, s.platform, s.country): (
            s.first_at,
            s.last_at,
            s.events,
            frozenset(s.names),
            s.last_name,
        )
        for s in SessionSlice.objects.filter(app=app)
    }


class SessionSlicesTest(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="owner", password="pw")
        self.app = App.objects.create(name="Lullgate", user=user)
        self.other = App.objects.create(name="Driftnook", user=user)
        self.start = datetime(2026, 10, 20, 21, 50, tzinfo=UTC)

    def events(self, app, count, seed):
        rng = random.Random(seed)
        return [
            Event(
                app=app,
                event_name=rng.choice(["opened", "paywall", "buy", "share"]),
                timestamp=self.start + timedelta(seconds=rng.randrange(0, 7200)),
                session_id=rng.choice([None, "", *(f"s{n:02d}" for n in range(12))]),
                platform=rng.choice([None, "iOS", "Android"]),
                country=rng.choice([None, "SE", "DE"]),
            )
            for _ in range(count)
        ]

    def check(self):
        for app in (self.app, self.other):
            self.assertEqual(stored(app), expected(app))

    def test_inserted_one_at_a_time_and_in_bulk(self):
        for event in self.events(self.app, 40, 1):
            event.save()
        Event.objects.bulk_create(self.events(self.app, 300, 2))
        Event.objects.bulk_create(self.events(self.other, 100, 3))
        self.check()
        self.assertGreater(SessionSlice.objects.filter(app=self.app).count(), 20)

    def test_an_event_from_before_lands_in_its_own_quarter(self):
        Event.objects.bulk_create(self.events(self.app, 50, 4))
        Event.objects.create(
            app=self.app,
            event_name="opened",
            timestamp=self.start - timedelta(days=3),
            session_id="s01",
        )
        self.check()

    def test_the_latest_event_names_the_slice_and_a_tie_takes_the_greater_name(self):
        at = self.start + timedelta(minutes=4)  # 21:54, in the quarter from 21:45
        for name, moment in (("beta", at), ("alpha", at), ("opened", at - timedelta(minutes=3))):
            Event.objects.create(app=self.app, event_name=name, timestamp=moment, session_id="s01")
        self.assertEqual(SessionSlice.objects.get(app=self.app).last_name, "beta")
        self.check()

    def test_deleted_and_changed_events(self):
        Event.objects.bulk_create(self.events(self.app, 300, 5))
        Event.objects.bulk_create(self.events(self.other, 100, 6))
        Event.objects.filter(app=self.app, event_name="share").delete()
        self.check()
        Event.objects.filter(app=self.app, event_name="paywall").update(
            timestamp=self.start + timedelta(minutes=1)
        )
        self.check()
        Event.objects.filter(app=self.app, session_id="s03").update(platform="Web")
        self.check()
        Event.objects.filter(app=self.app).delete()
        self.assertFalse(SessionSlice.objects.filter(app=self.app).exists())
        self.check()

    def test_the_retention_purge(self):
        Event.objects.bulk_create(self.events(self.app, 300, 7))
        Event.objects.filter(
            app=self.app, timestamp__lt=self.start + timedelta(minutes=37)
        ).delete()
        self.check()

    def test_an_apps_removal_takes_its_slices(self):
        Event.objects.bulk_create(self.events(self.app, 100, 8))
        Event.objects.bulk_create(self.events(self.other, 100, 9))
        self.app.delete()
        self.assertFalse(SessionSlice.objects.exclude(app=self.other).exists())
        self.assertEqual(stored(self.other), expected(self.other))

    def test_events_now_are_in_this_quarter(self):
        Event.objects.create(
            app=self.app, event_name="opened", timestamp=timezone.now(), session_id="s1"
        )
        self.assertEqual(SessionSlice.objects.get(app=self.app).quarter, quarter(timezone.now()))


class NightlyComparisonTest(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="owner", password="pw")
        self.app = App.objects.create(name="Moonpond", user=user)

    def add(self, minutes_ago, name="opened", session="s1"):
        Event.objects.create(
            app=self.app,
            event_name=name,
            timestamp=timezone.now() - timedelta(minutes=minutes_ago),
            session_id=session,
        )

    def test_nothing_to_do_when_the_slices_are_exact(self):
        for minutes in (30, 70, 600, 1500):
            self.add(minutes)
        self.assertEqual(slices.compare(), 0)

    def test_a_slice_left_behind_is_counted_again(self):
        self.add(60)
        self.add(61, "paywall")
        self.add(62, "buy", session="s2")
        # One slice lost and one miscounted, as a race or a write past the triggers could leave
        SessionSlice.objects.filter(app=self.app, session_id="s2").delete()
        SessionSlice.objects.filter(app=self.app, session_id="s1").update(events=99)
        self.assertGreater(slices.compare(), 0)
        self.assertEqual(stored(self.app), expected(self.app))
        self.assertEqual(slices.compare(), 0)

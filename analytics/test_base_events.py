"""sessions_per() gives what COUNT(DISTINCT session_id) gave, periods included, in their zone
(analytics/base_events.py)."""

import random
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.db.models.functions import TruncDay, TruncWeek
from django.test import TestCase
from django.utils import timezone

from analytics.base_events import session_count, sessions_per, slices_in
from analytics.date_utils import parse_date_range
from analytics.models import App, Event

ZONE = ZoneInfo("Asia/Kolkata")


class SessionsPerTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = User.objects.create_user(username="owner", password="pw")
        cls.app = App.objects.create(name="Lullgate", user=user)
        rng = random.Random(7)
        start = timezone.now() - timedelta(days=20)
        Event.objects.bulk_create(
            Event(
                app=cls.app,
                event_name=rng.choice(["open", "paywall", "buy"]),
                timestamp=start + timedelta(minutes=rng.randrange(0, 20 * 24 * 60)),
                session_id=rng.choice([None, "", *(f"s{n}" for n in range(60))]),
                platform=rng.choice([None, "iOS", "Android"]),
            )
            for _ in range(900)
        )

    def check(self, trunc, keys):
        events = Event.objects.filter(app=self.app).annotate(period=trunc("timestamp", tzinfo=ZONE))
        converted = Q(event_name="buy")
        want = {
            tuple(row[k] for k in keys): (row["s"], row["e"], row["c"])
            for row in events.values(*keys).annotate(
                s=Count("session_id", distinct=True),
                e=Count("id"),
                c=Count("session_id", distinct=True, filter=converted),
            )
        }
        got = {
            tuple(row[k] for k in keys): (row["sessions"], row["events"], row["converting"])
            for row in sessions_per(events, keys, converted=converted)
        }
        self.assertEqual(got, want)
        self.assertTrue(all(key[0].tzinfo is not None for key in got))

    def test_days_and_platforms(self):
        self.check(TruncDay, ["period"])
        self.check(TruncDay, ["period", "platform"])

    def test_weeks(self):
        self.check(TruncWeek, ["period"])


class SlicesCountAsTheEventsTest(TestCase):
    """Every count read from the session slices equals the same count over the events, in time
    zones whose offset is a half or a quarter of an hour, for any range of whole days."""

    @classmethod
    def setUpTestData(cls):
        user = User.objects.create_user(username="owner", password="pw")
        cls.app = App.objects.create(name="Lumenrest", user=user)
        rng = random.Random(11)
        start = timezone.now() - timedelta(days=12)
        Event.objects.bulk_create(
            Event(
                app=cls.app,
                event_name=rng.choice(["open", "paywall", "buy"]),
                timestamp=start + timedelta(seconds=rng.randrange(0, 12 * 86400)),
                session_id=rng.choice([None, "", *(f"s{n}" for n in range(80))]),
                platform=rng.choice([None, "iOS", "Android"]),
                country=rng.choice([None, "IN", "NP"]),
            )
            for _ in range(1500)
        )

    def test_days_weeks_platforms_and_conversions(self):
        for zone_name in ("Asia/Kolkata", "Asia/Kathmandu", "America/St_Johns", "UTC"):
            zone = ZoneInfo(zone_name)
            today = timezone.now().astimezone(zone).date()
            start, end = parse_date_range(
                (today - timedelta(days=9)).isoformat(),
                (today - timedelta(days=2)).isoformat(),
                zone_name,
            )
            events = Event.objects.filter(app=self.app, timestamp__gte=start, timestamp__lte=end)
            slices = slices_in(self.app, start, end)
            for trunc in (TruncDay, TruncWeek):
                for keys in (["period"], ["period", "platform"], ["period", "country"]):
                    want = {
                        tuple(row[k] for k in keys): (
                            row["sessions"],
                            row["events"],
                            row["converting"],
                        )
                        for row in sessions_per(
                            events.annotate(period=trunc("timestamp", tzinfo=zone)),
                            keys,
                            converted=Q(event_name="buy"),
                        )
                    }
                    got = {
                        tuple(row[k] for k in keys): (
                            row["sessions"],
                            row["events"],
                            row["converting"],
                        )
                        for row in sessions_per(
                            slices.annotate(period=trunc("quarter", tzinfo=zone)),
                            keys,
                            converted=Q(names__overlap=["buy"]),
                        )
                    }
                    self.assertEqual(got, want, (zone_name, trunc.__name__, keys))
            self.assertEqual(
                session_count(slices), events.values("session_id").distinct().count(), zone_name
            )

    def test_the_funnels_sessions_with_a_step_and_its_filters(self):
        start, end = parse_date_range(None, None, "UTC")
        for names, country, platform in (
            (["open", "buy"], None, None),
            (["paywall"], ["IN"], None),
            (["buy", "paywall"], None, ["iOS"]),
        ):
            events = (
                Event.objects.filter(app=self.app, event_name__in=names)
                .exclude(session_id__isnull=True)
                .exclude(session_id="")
            )
            slices = (
                slices_in(self.app)
                .filter(names__overlap=names)
                .exclude(session_id__isnull=True)
                .exclude(session_id="")
            )
            if country:
                events, slices = (
                    events.filter(country__in=country),
                    slices.filter(country__in=country),
                )
            if platform:
                events = events.filter(platform__in=platform)
                slices = slices.filter(platform__in=platform)
            self.assertEqual(session_count(slices), events.values("session_id").distinct().count())

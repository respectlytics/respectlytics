"""A range and its periods are the reader's own (the dashboard sends tz=<their zone>): an event a
few minutes after local midnight belongs to the local day it happened on, and no period starts
before the range. Until 2026-10-25 the range was read in the reader's zone and its periods cut
in UTC, so a reader in Stockholm saw every 30-day chart open on a day of two hours and each day
shifted by the offset, in the Overview's events and sessions, the conversions over time and the
segments' periods (found while photographing the dashboard for the homepage)."""

from datetime import UTC, datetime

from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APITestCase

from analytics.models import App, Event

# 00:30 and 10:00 on 11 March in Stockholm (UTC+1): 23:30 on the 10th and 09:00 on the 11th in UTC
TIMES = (datetime(2026, 3, 10, 23, 30, tzinfo=UTC), datetime(2026, 3, 11, 9, 0, tzinfo=UTC))
RANGE = {"from": "2026-03-11", "to": "2026-03-11"}


class ReadersOwnDaysTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="owner", password="pw")
        self.app = App.objects.create(name="Atlas", user=self.user)
        self.client.force_login(self.user)
        self.client.credentials(HTTP_X_APP_KEY=str(self.app.id))
        for n, moment in enumerate(TIMES):
            for name in ("app_open", "purchase"):
                Event.objects.create(
                    app=self.app,
                    event_name=name,
                    session_id=f"s{n}",
                    timestamp=moment,
                    platform="ios",
                    country="SE",
                )

    def get(self, path, tz, **params):
        response = self.client.get(path, {**RANGE, "tz": tz, **params})
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.data

    def test_the_overviews_events_by_day(self):
        days = self.get("/api/v1/events/summary/", "Europe/Stockholm")["events_by_day"]
        self.assertEqual([(d["date"], d["count"]) for d in days], [("2026-03-11", 4)])
        # In UTC the same range holds only the event of 09:00
        days = self.get("/api/v1/events/summary/", "UTC")["events_by_day"]
        self.assertEqual([(d["date"], d["count"]) for d in days], [("2026-03-11", 2)])

    def test_the_overviews_sessions_by_day(self):
        data = self.get("/api/v1/analytics/dau/", "Europe/Stockholm")
        periods = [(p["period"], p["unique_sessions"]) for p in data["active_sessions"]]
        self.assertEqual(periods, [("2026-03-11", 2)])
        # the session lengths, cut in SQL, land on the same local day as the sessions
        self.assertEqual(data["active_sessions"][0]["sessions_with_duration"], 2)

    def test_the_conversions_by_day(self):
        data = self.get(
            "/api/v1/analytics/conversions/", "Europe/Stockholm", conversion_events="purchase"
        )
        periods = [(p["period"], p["conversions"]) for p in data["conversions"]]
        self.assertEqual(periods, [("2026-03-11", 2)])

    def test_the_segments_by_day(self):
        for segment_by in ("platform", "depth"):
            with self.subTest(segment_by=segment_by):
                data = self.get(
                    "/api/v1/analytics/segments/",
                    "Europe/Stockholm",
                    segment_by=segment_by,
                    conversion_events="purchase",
                )
                periods = {p["period"] for s in data["segments"] for p in s["periods"]}
                self.assertEqual(periods, {"2026-03-11"})

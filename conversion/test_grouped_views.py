"""Every view that names events reads them through the app's groups when asked
(`group_events=true`, which the dashboard sends), and counts a session once for a group:
paths, drop-off points, boosters and blockers, and a funnel whose step is a group. Without it,
an API caller reads every event by its own name, as before (analytics/event_groups.py)."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from analytics import event_groups
from analytics.models import App, Event

SESSIONS = {
    "s1": ["app_open", "paywall_view", "purchase_light"],
    "s2": ["app_open", "paywall_view", "purchase_pro"],
    "s3": ["app_open", "share_twitter"],
    "s4": ["app_open", "share_facebook"],
    "s5": ["app_open", "share_twitter", "share_facebook"],
}
CONVERSIONS = "purchase_light,purchase_pro"


class GroupedViewsTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="owner", password="pw")
        self.app = App.objects.create(name="Shop", user=self.user)
        self.client.force_login(self.user)
        self.client.credentials(HTTP_X_APP_KEY=str(self.app.id))
        start = timezone.now() - timedelta(hours=1)
        for session, names in SESSIONS.items():
            for i, name in enumerate(names):
                Event.objects.create(
                    app=self.app,
                    event_name=name,
                    session_id=session,
                    timestamp=start + timedelta(minutes=i),
                )

    def get(self, path, grouped, **params):
        if grouped:
            params["group_events"] = "true"
        response = self.client.get(f"/api/v1/analytics/{path}/", params)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.data

    def test_paths_of_one_group_are_one_path(self):
        data = self.get("conversion-paths", True, conversion_events=CONVERSIONS)
        paths = [(p["path"], p["sessions"]) for p in data["top_conversion_paths"]]
        self.assertEqual(paths, [(["app_open", "paywall_view", "purchase"], 2)])
        self.assertTrue(data["filters"]["group_events"])
        data = self.get("conversion-paths", False, conversion_events=CONVERSIONS)
        self.assertEqual(
            sorted(p["path"][-1] for p in data["top_conversion_paths"]),
            ["purchase_light", "purchase_pro"],
        )

    def test_a_paths_timings_line_up_with_its_steps(self):
        """A path cut to max_path_length keeps the timings of the steps it kept."""
        data = self.get("conversion-paths", True, conversion_events=CONVERSIONS, max_path_length=2)
        path = data["top_conversion_paths"][0]
        self.assertEqual(path["path"], ["paywall_view", "purchase"])
        self.assertEqual(
            path["step_timings"], [{"from": "paywall_view", "to": "purchase", "avg_minutes": 1.0}]
        )
        self.assertEqual(path["avg_duration_minutes"], 1.0)

    def test_drop_off_points_of_one_group_add_up_and_a_session_counts_once(self):
        data = self.get("drop-off", True, conversion_events=CONVERSIONS, min_sessions=1)
        points = {p["event"]: p for p in data["drop_off_points"]}
        self.assertEqual(set(points), {"share"})
        self.assertEqual(points["share"]["sessions_dropped"], 3)
        # s5 sent both share events: it is one of the three non-converting sessions, not two
        self.assertEqual(points["share"]["converter_comparison"]["non_converters_event_rate"], 1)
        common = {e["event"]: e for e in data["events_more_common_in_non_converters"]}
        self.assertEqual(common["share"]["non_converter_rate"], 1)
        data = self.get("drop-off", False, conversion_events=CONVERSIONS, min_sessions=1)
        dropped = {p["event"]: p["sessions_dropped"] for p in data["drop_off_points"]}
        self.assertEqual(dropped, {"share_facebook": 2, "share_twitter": 1})

    def test_a_group_must_reach_min_sessions_as_a_whole(self):
        data = self.get("drop-off", True, conversion_events=CONVERSIONS, min_sessions=3)
        self.assertEqual([p["event"] for p in data["drop_off_points"]], ["share"])
        data = self.get("drop-off", False, conversion_events=CONVERSIONS, min_sessions=3)
        self.assertEqual(data["drop_off_points"], [])

    def test_boosters_and_blockers_count_a_session_once_and_leave_out_the_conversion_group(self):
        data = self.get("event-correlation", True, conversion_events=CONVERSIONS, min_sessions=1)
        rows = data["positive_correlations"] + data["negative_correlations"]
        named = {r["event"]: r for r in rows}
        self.assertEqual(named["share"]["sessions_with_event"], 3)
        everything = set(named) | set(data["neutral_events"])
        self.assertNotIn("purchase", everything)
        self.assertNotIn("share_twitter", everything)
        data = self.get("event-correlation", False, conversion_events=CONVERSIONS, min_sessions=1)
        rows = data["positive_correlations"] + data["negative_correlations"]
        named = {r["event"]: r for r in rows}
        self.assertEqual(named["share_twitter"]["sessions_with_event"], 2)

    def test_a_funnel_step_may_be_a_group(self):
        def funnel(grouped):
            params = {"steps": "app_open,purchase"}
            if grouped:
                params["group_events"] = "true"
            response = self.client.get("/api/v1/events/funnel/", params)
            self.assertEqual(response.status_code, 200, response.content[:300])
            return [s["count"] for s in response.data["funnel"]]

        self.assertEqual(funnel(True), [5, 2])
        self.assertEqual(funnel(False), [5, 0])

    def test_a_funnel_is_served_from_the_cache_the_second_time(self):
        self.client.get("/api/v1/events/funnel/", {"steps": "app_open,paywall_view"})
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/v1/events/funnel/", {"steps": "app_open,paywall_view"})
        self.assertEqual([s["count"] for s in response.data["funnel"]], [5, 2])
        self.assertFalse([q for q in queries if "funnel_progress" in q["sql"]])

    def test_a_step_timing_step_may_be_a_group(self):
        data = self.get("step-timing", True, steps="paywall_view,purchase")
        self.assertEqual(data["funnel_summary"]["sessions_with_all_steps"], 2)
        data = self.get("step-timing", False, steps="paywall_view,purchase")
        self.assertEqual(data["funnel_summary"]["sessions_with_all_steps"], 0)

    def test_a_change_to_the_groups_shows_at_once(self):
        self.get("conversion-paths", True, conversion_events=CONVERSIONS)
        event_groups.change(self.app, "separate", "purchase", [], set())
        data = self.get("conversion-paths", True, conversion_events=CONVERSIONS)
        self.assertEqual(len(data["top_conversion_paths"]), 2)


class SegmentsTakeNamesAsParametersTest(APITestCase):
    """A conversion event's name is the caller's text: it reaches the depth and hour queries as
    a parameter, never as SQL (until 2026-10-24 it was pasted into the query)."""

    def setUp(self):
        cache.clear()
        user = User.objects.create_user(username="owner", password="pw")
        self.app = App.objects.create(name="Shop", user=user)
        self.client.force_login(user)
        self.client.credentials(HTTP_X_APP_KEY=str(self.app.id))
        now = timezone.now() - timedelta(minutes=5)
        Event.objects.create(app=self.app, event_name="it's done", session_id="a", timestamp=now)
        Event.objects.create(app=self.app, event_name="app_open", session_id="b", timestamp=now)

    def test_a_quote_in_a_name_is_a_name(self):
        for segment_by in ("depth", "hour"):
            for name, conversions in (("it's done", 1), ("x') OR 1=1 OR ('", 0)):
                response = self.client.get(
                    "/api/v1/analytics/segments/",
                    {"conversion_events": name, "segment_by": segment_by},
                )
                self.assertEqual(response.status_code, 200, response.content[:300])
                total = sum(s["summary"]["total_conversions"] for s in response.data["segments"])
                self.assertEqual(total, conversions, (segment_by, name))


class ConversionRatesCountSessionsTest(APITestCase):
    """A rate is sessions with a conversion event over sessions, on the globe, in the segments
    by platform and country and in the conversion summary: a session that buys twice is one
    converting session, so no rate passes 100% (until 2026-10-24 these counted the events)."""

    def setUp(self):
        cache.clear()
        user = User.objects.create_user(username="owner", password="pw")
        self.app = App.objects.create(name="Shop", user=user)
        self.client.force_login(user)
        self.client.credentials(HTTP_X_APP_KEY=str(self.app.id))
        start = timezone.now() - timedelta(hours=1)
        sessions = {"a": ["app_open", "purchase", "purchase"], "b": ["app_open"]}
        for session, names in sessions.items():
            for i, name in enumerate(names):
                Event.objects.create(
                    app=self.app,
                    event_name=name,
                    session_id=session,
                    timestamp=start + timedelta(minutes=i),
                    country="SE",
                    platform="ios",
                )
        self.today = timezone.now().date().isoformat()

    def get(self, path, **params):
        response = self.client.get(path, {"conversion_events": "purchase", **params})
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.data

    def test_the_globe(self):
        dates = {"from": self.today, "to": self.today, "app_key": str(self.app.id)}
        data = self.get("/api/v1/analytics/globe-stats/", **dates)
        [sweden] = data["data"]
        self.assertEqual((sweden["sessions"], sweden["conversions"]), (2, 1))
        self.assertEqual(sweden["conversion_rate"], 50.0)

    def test_the_segments_by_platform_and_country(self):
        for segment_by in ("platform", "country"):
            data = self.get("/api/v1/analytics/segments/", segment_by=segment_by)
            [segment] = data["segments"]
            self.assertEqual(segment["summary"]["total_conversions"], 1, segment_by)
            self.assertEqual(segment["summary"]["conversion_rate"], 0.5, segment_by)

    def test_the_conversion_summary(self):
        data = self.get("/api/v1/analytics/conversions/", **{"from": self.today, "to": self.today})
        self.assertEqual(data["summary"]["total_conversions"], 1)
        self.assertEqual(data["summary"]["avg_conversion_rate"], 0.5)

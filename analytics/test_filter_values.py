"""The filter options' countries and platforms, read by index probes, are every value the app's
events carry and no other app's (analytics/filter_values.py)."""

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from analytics.filter_values import countries_and_platforms
from analytics.models import App, Event


class FilterValuesTest(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="owner", password="pw")
        self.app = App.objects.create(name="Moonpond", user=user)
        other = App.objects.create(name="Lullgate", user=user)
        now = timezone.now()
        rows = [
            ("SE", "iOS"),
            ("SE", "iOS"),
            ("SE", "Android"),
            ("SE", None),
            ("DE", None),
            ("US", "Web"),
            (None, "macOS"),  # no country: still a platform
            (None, None),
            ("", ""),
            ("JP", "ios"),  # sent before platforms were named on intake
        ]
        Event.objects.bulk_create(
            Event(app=self.app, event_name="opened", timestamp=now, country=c, platform=p)
            for c, p in rows
        )
        Event.objects.create(
            app=other, event_name="opened", timestamp=now, country="BR", platform="Linux"
        )

    def test_every_value_the_app_sent_and_no_other_apps(self):
        countries, platforms = countries_and_platforms(self.app.id)
        self.assertEqual(countries, ["DE", "JP", "SE", "US"])
        self.assertEqual(platforms, ["Android", "Web", "iOS", "ios", "macOS"])

    def test_an_app_with_no_events(self):
        user = User.objects.create_user(username="new", password="pw")
        app = App.objects.create(name="Lumenrest", user=user)
        self.assertEqual(countries_and_platforms(app.id), ([], []))

    def test_the_filter_options_answer_in_one_query_over_the_events(self):
        self.client.force_login(self.app.user)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                "/api/v1/events/filter-options/", HTTP_X_APP_KEY=str(self.app.id)
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["filters"]["countries"], ["DE", "JP", "SE", "US"])
        self.assertEqual(response.json()["filters"]["event_names"], ["opened"])
        reads = [q["sql"] for q in queries.captured_queries if "analytics_event" in q["sql"]]
        self.assertEqual(len(reads), 2)  # the pairs, and known_names' probe

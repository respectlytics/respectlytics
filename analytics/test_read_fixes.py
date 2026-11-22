"""Four read paths, each made safe to be read often and by anything:
an unknown time zone cannot make cache rows of its own, a bad limit is a plain 400 and never a
500, the globe's time limit ends with its request, and the event names are every name sent."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from .date_utils import get_cache_key_with_timezone
from .models import App, Event, SecretKey


class ReadFixesTest(APITestCase):
    def setUp(self):
        owner = User.objects.create_user("dev@example.com", "dev@example.com", "x-unused-1")
        self.app = App.objects.create(name="Moonpond", user=owner)
        _, key = SecretKey.make(owner)
        self.client = APIClient(raise_request_exception=False)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {key}", HTTP_X_APP_KEY=str(self.app.id))

    def test_an_unknown_time_zone_shares_utcs_cache_key(self):
        self.assertEqual(
            get_cache_key_with_timezone("summary", "a", "2026-10-01", "2026-10-07", "Mars/Base"),
            get_cache_key_with_timezone("summary", "a", "2026-10-01", "2026-10-07", "UTC"),
        )

    def test_a_limit_that_is_not_a_number_is_a_400(self):
        for limit in ("ten", "", "1e9x"):
            response = self.client.get("/api/v1/events/geo-summary/", {"limit": limit})
            self.assertEqual(response.status_code, 400, limit)

    def test_the_globes_time_limit_ends_with_its_request(self):
        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            before = cursor.fetchone()[0]
        window = {"app_key": str(self.app.id), "from": "2026-10-01", "to": "2026-10-07"}
        response = self.client.get("/api/v1/analytics/globe-stats/", window)
        self.assertEqual(response.status_code, 200)
        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            self.assertEqual(cursor.fetchone()[0], before)

    def test_event_names_include_ones_older_than_ninety_days(self):
        long_ago = timezone.now() - timedelta(days=200)
        Event.objects.create(app=self.app, event_name="old_one", timestamp=long_ago)
        Event.objects.create(app=self.app, event_name="new_one", timestamp=timezone.now())
        response = self.client.get("/api/v1/events/event-types/")
        self.assertEqual(response.json()["event_types"], ["new_one", "old_one"])

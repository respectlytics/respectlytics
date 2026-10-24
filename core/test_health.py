"""/healthz: what the uptime watchdog and the deploy gate read (core/health.py)."""

from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.core.cache import caches
from django.test import TestCase, override_settings
from django.utils import timezone

from analytics.middleware import HEALTH_CHECK_PATHS

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


class HealthzTests(TestCase):
    def test_answers_ok_and_nothing_else(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertIn("no-cache", response["Cache-Control"])

    def test_a_database_failure_is_a_503_that_names_nothing(self):
        with mock.patch("core.health.connection.cursor", side_effect=RuntimeError("secret detail")):
            with self.assertLogs("core.health", "ERROR"):
                response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertNotIn(b"secret detail", response.content)

    def test_only_get(self):
        self.assertEqual(self.client.post("/healthz").status_code, 405)


@override_settings(TESTING=False, CACHES=LOCMEM)
class HealthzBeforeBansTests(TestCase):
    """A ban can never make the service look down to the watchdog."""

    def setUp(self):
        caches["default"].clear()

    def test_is_answered_for_a_banned_address(self):
        self.assertIn("/healthz", HEALTH_CHECK_PATHS)
        blocked = SimpleNamespace(kind="attack", expires_at=timezone.now() + timedelta(days=1))
        with mock.patch("analytics.middleware.active_block", return_value=blocked):
            self.assertEqual(self.client.get("/healthz").status_code, 200)
            self.assertNotEqual(self.client.get("/login/").status_code, 200)

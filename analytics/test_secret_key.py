"""The secret key reads, exports and deletes an account's data through the API, in both
editions (analytics.models.SecretKey, analytics/authentication.py SecretKeyAuthentication).

Since 2026-10-22 the app key, which ships inside every copy of an app, may only send events
(test_app_key_scope.py), which left a developer without a browser no way to read or delete.
The secret key stays with the developer: sent as `Authorization: Bearer`, with the app key
naming which of the account's apps, made and revoked on the account page.
"""

import sys
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from django.views.debug import get_exception_reporter_class
from rest_framework.test import APIClient, APITestCase

from .models import App, DeletionLog, Event, SecretKey
from .test_app_key_scope import DELETES, READS

DAY = {"date_from": "2026-10-01", "date_to": "2026-10-31"}


class SecretKeyModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("dev@example.com", "dev@example.com", "x-unused-1")

    def test_only_the_digest_is_kept(self):
        row, key = SecretKey.make(self.user)
        self.assertTrue(key.startswith("rl_secret_"))
        self.assertEqual(len(key), len("rl_secret_") + 40)
        self.assertNotIn(key, str(SecretKey.objects.filter(pk=row.pk).values().get()))
        self.assertEqual(SecretKey.find(key), row)
        self.assertEqual(row.start, key[:14])

    def test_a_key_that_was_never_made_finds_nothing(self):
        _, key = SecretKey.make(self.user)
        for wrong in (key[:-1] + ("a" if key[-1] != "a" else "b"), key[:-1], "", "rl_secret_"):
            with self.subTest(wrong=wrong):
                self.assertIsNone(SecretKey.find(wrong))

    def test_use_is_noted_at_most_once_an_hour(self):
        row, _ = SecretKey.make(self.user)
        row.note_use()
        row.refresh_from_db()
        first = row.last_used_at
        self.assertIsNotNone(first)
        row.note_use()
        row.refresh_from_db()
        self.assertEqual(row.last_used_at, first)
        SecretKey.objects.filter(pk=row.pk).update(last_used_at=first - timedelta(hours=2))
        row.refresh_from_db()
        row.note_use()
        row.refresh_from_db()
        self.assertGreater(row.last_used_at, first)


class SecretKeyApiTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.owner = User.objects.create_user("owner@example.com", "owner@example.com", "x-1")
        self.app = App.objects.create(name="Recipe Box", user=self.owner)
        Event.objects.create(
            app=self.app, event_name="purchase_pro", timestamp="2026-10-20T10:00:00Z"
        )
        _, self.secret = SecretKey.make(self.owner)
        self.client = APIClient(enforce_csrf_checks=True)

    def use(self, secret=None, app_key=None):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {secret or self.secret}",
            HTTP_X_APP_KEY=app_key or str(self.app.id),
        )

    def test_it_answers_every_read(self):
        self.use()
        for path in READS:
            with self.subTest(path=path):
                self.assertNotIn(self.client.get(path).status_code, (401, 403))
        response = self.client.get("/api/v1/events/summary/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_events"], 1)

    def test_it_deletes_without_a_csrf_token_and_the_deletion_is_logged(self):
        self.use()
        preview = self.client.post(DELETES[0], DAY, format="json")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["events_matching"], 1)
        response = self.client.post(DELETES[1], DAY, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["events_deleted"], 1)
        self.assertFalse(Event.objects.filter(app=self.app).exists())
        log = DeletionLog.objects.get(pk=response.data["deletion_id"])
        self.assertEqual((log.app, log.deleted_by), (self.app, self.owner))
        history = self.client.get("/api/v1/events/deletions/")
        self.assertEqual(history.status_code, 200)
        self.assertIn(response.data["deletion_id"], str(history.data))

    def test_another_accounts_app_is_refused(self):
        stranger = User.objects.create_user("s@example.com", "s@example.com", "x-2")
        theirs = App.objects.create(name="Theirs", user=stranger)
        Event.objects.create(app=theirs, event_name="secret_event", timestamp=timezone.now())
        self.use(app_key=str(theirs.id))
        for path in READS:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)
                self.assertNotIn(b"secret_event", response.content)
        self.assertEqual(self.client.post(DELETES[1], DAY, format="json").status_code, 401)
        self.assertTrue(Event.objects.filter(app=theirs).exists())

    def test_a_wrong_revoked_or_missing_key_is_refused(self):
        row = SecretKey.find(self.secret)
        _, other = SecretKey.make(self.owner)
        SecretKey.objects.filter(pk=SecretKey.find(other).pk).delete()
        for secret in (other, self.secret[:-2] + "zz", str(self.app.id)):
            with self.subTest(secret=secret[:14]):
                self.use(secret=secret)
                response = self.client.get("/api/v1/events/summary/")
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response["WWW-Authenticate"], 'Bearer realm="api"')
        self.assertIsNotNone(row)

    def test_the_app_must_be_named(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.secret}")
        response = self.client.get("/api/v1/events/summary/")
        self.assertEqual(response.status_code, 401)
        self.assertIn("X-App-Key", str(response.data))

    def test_a_key_in_the_address_is_not_read(self):
        url = f"/api/v1/events/summary/?app_key={self.app.id}&secret_key={self.secret}"
        self.assertEqual(self.client.get(url).status_code, 401)

    def test_a_deactivated_account_is_refused(self):
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        self.use()
        self.assertEqual(self.client.get("/api/v1/events/summary/").status_code, 401)

    def test_an_error_report_never_carries_the_key(self):
        request = RequestFactory().get(
            "/api/v1/events/summary/", HTTP_AUTHORIZATION=f"Bearer {self.secret}"
        )
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            reporter = get_exception_reporter_class(request)(request, *sys.exc_info())
        report = reporter.get_traceback_text() + reporter.get_traceback_html()
        self.assertIn("RuntimeError", report)
        self.assertNotIn(self.secret, report)


class AccountPageTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("dev@example.com", "dev@example.com", "x-unused-1")
        self.app = App.objects.create(name="Recipe Box", user=self.user)
        self.client.force_login(self.user)
        self.page = reverse("account_api_keys")

    def test_a_new_key_is_shown_once_and_never_cached(self):
        response = self.client.post(self.page)
        self.assertEqual(response.status_code, 200)
        key = response.context["new_key"]
        self.assertContains(response, key)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(SecretKey.find(key).user, self.user)
        again = self.client.get(self.page)
        self.assertNotContains(again, key)
        self.assertContains(again, key[:14])
        self.assertContains(again, str(self.app.id))

    def test_revoking_ends_the_key(self):
        row, key = SecretKey.make(self.user)
        self.client.post(reverse("account_api_key_revoke", args=[row.pk]))
        self.assertIsNone(SecretKey.find(key))

    def test_another_accounts_key_cannot_be_revoked(self):
        other = User.objects.create_user("o@example.com", "o@example.com", "x-unused-2")
        row, _ = SecretKey.make(other)
        self.client.post(reverse("account_api_key_revoke", args=[row.pk]))
        self.assertTrue(SecretKey.objects.filter(pk=row.pk).exists())

    def test_an_account_holds_five_keys(self):
        for _ in range(SecretKey.LIMIT):
            SecretKey.make(self.user)
        response = self.client.post(self.page, follow=True)
        self.assertEqual(SecretKey.objects.filter(user=self.user).count(), SecretKey.LIMIT)
        self.assertContains(response, "Revoke one")
        self.assertNotContains(response, "Create secret key")

    def test_signed_out_people_are_sent_to_sign_in(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.page).status_code, 302)
        self.assertFalse(SecretKey.objects.exists())


class SecretKeyInLogsTest(TestCase):
    def test_a_logged_key_keeps_only_its_start(self):
        from .logging_filters import SanitizeAppKeyFilter

        user = User.objects.create_user("dev@example.com", "dev@example.com", "x-unused-1")
        _, key = SecretKey.make(user)
        text = SanitizeAppKeyFilter().sanitize_text(f"Authorization: Bearer {key}")
        self.assertNotIn(key, text)
        self.assertIn(key[:14] + "...", text)

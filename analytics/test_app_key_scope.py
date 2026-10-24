"""The app key may only send events.

It ships inside every copy of a customer's app, so anyone can pull it out of a published
app. Until 2026-10-22 it also answered every read, export and delete endpoint, so whoever
had it could read, download or delete that app's data. Now only the signed-in owner can
(analytics/authentication.py, AppOwnerSessionAuthentication).
"""

from django.contrib.auth.models import User
from rest_framework.test import APIClient, APITestCase

from .models import App, Event

READS = [
    "/api/v1/events/summary/",
    "/api/v1/events/count/",
    "/api/v1/events/geo-summary/",
    "/api/v1/events/funnel/?steps=a,b",
    "/api/v1/events/event-types/",
    "/api/v1/events/filter-options/",
    "/api/v1/events/export/",
    "/api/v1/events/recent-activity/",
    "/api/v1/events/deletions/",
    "/api/v1/analytics/dau/",
    "/api/v1/analytics/conversions/",
    "/api/v1/analytics/time-to-conversion/",
    "/api/v1/analytics/step-timing/",
    "/api/v1/analytics/conversion-paths/",
    "/api/v1/analytics/drop-off/",
    "/api/v1/analytics/event-correlation/",
    "/api/v1/analytics/segments/",
    "/api/v1/analytics/globe-stats/",
]
DELETES = ["/api/v1/events/delete/preview/", "/api/v1/events/delete/"]
SESSION = "3f9c2a7e5b1d4c8fa06e9b2d7c4a1f53"


class AppKeyScopeTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="x-unused-1")
        self.stranger = User.objects.create_user(username="stranger", password="x-unused-2")
        self.app = App.objects.create(name="Recipe Box", user=self.owner)
        self.key = str(self.app.id)
        Event.objects.create(
            app=self.app, event_name="purchase_pro", timestamp="2026-10-20T10:00:00Z"
        )

    def test_the_key_alone_still_sends_events(self):
        self.client.credentials(HTTP_X_APP_KEY=self.key)
        response = self.client.post(
            "/api/v1/events/", {"event_name": "app_open", "session_id": SESSION}, format="json"
        )
        self.assertEqual(response.status_code, 201)

    def test_the_key_alone_reads_nothing(self):
        for header, query in ((True, False), (False, True)):
            client = APIClient()
            if header:
                client.credentials(HTTP_X_APP_KEY=self.key)
            for path in READS:
                joiner = "&" if "?" in path else "?"
                url = f"{path}{joiner}app_key={self.key}" if query else path
                with self.subTest(path=path, header=header):
                    response = client.get(url)
                    self.assertEqual(response.status_code, 401)
                    self.assertNotIn(b"purchase_pro", response.content)

    def test_the_key_alone_deletes_nothing(self):
        self.client.credentials(HTTP_X_APP_KEY=self.key)
        for path in DELETES:
            with self.subTest(path=path):
                response = self.client.post(
                    path, {"event_names": ["purchase_pro"], "confirm": True}, format="json"
                )
                self.assertEqual(response.status_code, 401)
        self.assertEqual(Event.objects.filter(app=self.app).count(), 1)

    def test_another_signed_in_person_cannot_use_the_key(self):
        self.client.force_login(self.stranger)
        self.client.credentials(HTTP_X_APP_KEY=self.key)
        for path in READS:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)
        for path in DELETES:
            with self.subTest(path=path):
                response = self.client.post(path, {"event_names": ["purchase_pro"]}, format="json")
                self.assertEqual(response.status_code, 401)
        self.assertEqual(Event.objects.filter(app=self.app).count(), 1)

    def test_the_signed_in_owner_reads(self):
        self.client.force_login(self.owner)
        self.client.credentials(HTTP_X_APP_KEY=self.key)
        response = self.client.get("/api/v1/events/summary/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_events"], 1)

    def test_a_delete_from_the_owner_needs_the_csrf_token(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.owner)
        client.credentials(HTTP_X_APP_KEY=self.key)
        response = client.post(DELETES[1], {"event_names": ["purchase_pro"]}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertIn("CSRF", str(response.data))
        self.assertEqual(Event.objects.filter(app=self.app).count(), 1)

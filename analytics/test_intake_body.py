"""POST /api/v1/events/ takes one event as a JSON object. Any other body (an array, as the
Kotlin SDK before 3.1.0 sent its queue, a string, a number, null) is answered 400 with what to
send, never 500, and stores nothing."""

from django.contrib.auth.models import User
from rest_framework.test import APIClient, APITestCase

from .models import App, Event

SESSION = "3f9c2a7e5b1d4c8fa06e9b2d7c4a1f53"


class IntakeBodyTest(APITestCase):
    def setUp(self):
        owner = User.objects.create_user(username="owner", password="x-unused-1")
        self.app = App.objects.create(name="Shop", user=owner)
        self.client = APIClient(raise_request_exception=False)
        self.client.credentials(HTTP_X_APP_KEY=str(self.app.id))

    def post(self, body):
        return self.client.post("/api/v1/events/", body, content_type="application/json")

    def test_anything_but_one_object_is_400(self):
        one = f'{{"event_name": "app_open", "session_id": "{SESSION}"}}'
        for body in (f"[{one}, {one}]", "[]", '"app_open"', "42", "null", "true"):
            response = self.post(body)
            self.assertEqual(response.status_code, 400, body)
            self.assertIn("one event", response.json()["detail"], body)
        self.assertFalse(Event.objects.exists())

    def test_one_object_is_still_201(self):
        response = self.post(f'{{"event_name": "app_open", "session_id": "{SESSION}"}}')
        self.assertEqual(response.status_code, 201)

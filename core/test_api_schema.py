"""The OpenAPI schema URLs, which drf-yasg serves by renderer format.

drf-yasg's formats are 'json' and 'yaml' with no leading dot
(SWAGGER_USE_COMPAT_RENDERERS = False), so the URL patterns keep the dot
outside the captured group. These tests hold the public URLs to what the API
reference page links: /api/v1/reference/schema.json and .yaml, and the
staff-only /swagger.json, which stays a 404 for everyone else.
"""

import json
from unittest import skipIf, skipUnless

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APITestCase

from analytics.models import App, Event, SecretKey
from core.api_schema import APP_KEY, APP_KEY_OPERATIONS, SECRET_KEY, SECRET_KEY_OPERATIONS

COMMUNITY = getattr(settings, "RESPECTLYTICS_EDITION", None) == "community"


class SchemaUrlTests(TestCase):
    def test_the_public_schema_is_served_as_json_and_yaml(self):
        response = self.client.get("/api/v1/reference/schema.json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("json", response["Content-Type"])
        schema = json.loads(response.content)
        self.assertEqual(schema.get("swagger"), "2.0")
        self.assertTrue(schema.get("paths"))

        response = self.client.get("/api/v1/reference/schema.yaml")
        self.assertEqual(response.status_code, 200)
        self.assertIn("yaml", response["Content-Type"])
        self.assertIn(b"swagger:", response.content)

    def test_the_public_schema_shows_what_each_key_opens(self):
        # The app key sends events; the secret key reads and deletes. Every other endpoint is
        # the dashboard's own, behind the signed-in session.
        schema = json.loads(self.client.get("/api/v1/reference/schema.json").content)
        operations = {
            (schema.get("basePath", "") + path, method.upper()): op
            for path, methods in schema["paths"].items()
            for method, op in methods.items()
            if method in {"get", "post", "put", "patch", "delete"}
        }
        self.assertEqual(set(operations), APP_KEY_OPERATIONS | set(SECRET_KEY_OPERATIONS))
        for key, op in operations.items():
            with self.subTest(operation=key):
                wanted = APP_KEY if key in APP_KEY_OPERATIONS else SECRET_KEY
                self.assertEqual(op["security"], [{wanted: []}])
        self.assertEqual(set(schema["securityDefinitions"]), {APP_KEY, SECRET_KEY})
        self.assertNotIn("All API endpoints require", schema["info"]["description"])

    @skipIf(COMMUNITY, "respectlytics.com only: the community edition has no staff schema")
    def test_the_staff_schema_is_hidden_from_everyone_else(self):
        self.assertEqual(self.client.get("/swagger.json").status_code, 404)
        staff = User.objects.create_user("staff", "staff@example.com", "pw", is_staff=True)
        self.client.force_login(staff)
        response = self.client.get("/swagger.json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content).get("swagger"), "2.0")

    @skipUnless(COMMUNITY, "community edition only")
    def test_the_community_edition_serves_no_staff_schema_at_all(self):
        staff = User.objects.create_user("staff", "staff@example.com", "pw", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/swagger.json").status_code, 404)


def _shape(value):
    """The fields of an answer, and of the first item of every list in it, without values."""
    if isinstance(value, dict):
        return {key: _shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return None


class PublishedExamplesTest(APITestCase):
    """Every documented answer has exactly the fields the API returns."""

    def setUp(self):
        owner = User.objects.create_user("owner@example.com", "owner@example.com", "x-1")
        self.app = App.objects.create(name="Recipe Box", user=owner)
        for minute, name in enumerate(
            ["app_open", "recipe_saved", "purchase_pro", "purchase_light"]
        ):
            Event.objects.create(
                app=self.app,
                event_name=name,
                session_id="3f9c2a7e5b1d4c8fa06e9b2d7c4a1f53",
                timestamp=f"2026-10-20T10:0{minute}:00Z",
                platform="ios",
                country="SE",
            )
        _, secret = SecretKey.make(owner)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {secret}", HTTP_X_APP_KEY=str(self.app.id)
        )

    def answer(self, path, method):
        days = {"date_from": "2026-10-01", "date_to": "2026-10-31"}
        if method == "POST":
            return self.client.post(path, days, format="json")
        query = "?from=2026-10-01&to=2026-10-31&steps=app_open,purchase_pro&output=json"
        return self.client.get(path + query)

    @staticmethod
    def body(response):
        if hasattr(response, "data"):
            return response.data
        content = b"".join(response.streaming_content) if response.streaming else response.content
        return json.loads(content)

    def test_each_example_has_the_fields_of_a_real_answer(self):
        # The delete runs last, so the history has a deletion to show.
        order = sorted(SECRET_KEY_OPERATIONS, key=lambda k: k[0].endswith("/deletions/"))
        for path, method in order:
            example = SECRET_KEY_OPERATIONS[(path, method)][3]
            with self.subTest(operation=(path, method)):
                response = self.answer(path, method)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(_shape(self.body(response)), _shape(example))

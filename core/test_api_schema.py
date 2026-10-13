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

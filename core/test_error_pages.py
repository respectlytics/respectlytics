"""The site's own error pages render in both editions. The community edition has its own
(scripts/sync_to_oss.py puts them in place), and an error page that cannot render turns the
error into a 500: the community edition's 403 page once named a URL it does not have."""

from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.views import defaults

from core.csrf import csrf_failure


class ErrorPagesTest(TestCase):
    def request(self, method="get"):
        request = getattr(RequestFactory(), method)("/somewhere/")
        request.user = AnonymousUser()
        request.session = SessionStore()
        return request

    def test_each_renders_with_its_status(self):
        pages = {
            400: defaults.bad_request(self.request(), Exception()),
            403: defaults.permission_denied(self.request(), PermissionDenied()),
            404: defaults.page_not_found(self.request(), Exception()),
            "csrf": csrf_failure(self.request("post")),
        }
        for name, response in pages.items():
            with self.subTest(name):
                self.assertEqual(response.status_code, 403 if name == "csrf" else name)
                self.assertIn(b"Respectlytics", response.content)

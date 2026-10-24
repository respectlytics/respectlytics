"""A refused form never shows Django's bare "CSRF verification failed" page (core/csrf.py)."""

from django.contrib.auth.models import User
from django.test import Client, TestCase


class RefusedFormTest(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def test_a_sign_in_page_opens_again_with_one_line(self):
        for path in ["/login/", "/register/", "/password-reset/"]:
            response = self.client.post(path, {"email": "someone@example.com"})
            self.assertRedirects(response, f"{path}?expired=1", fetch_redirect_response=False)
            page = self.client.get(f"{path}?expired=1").content.decode()
            self.assertIn("This page had been open a while", page, path)

    def test_any_other_form_gets_the_sites_own_page(self):
        user = User.objects.create_user(username="owner", email="owner@example.com", password="pw")
        self.client.force_login(user)
        response = self.client.post("/account/profile/", {})
        self.assertEqual(response.status_code, 403)
        page = response.content.decode()
        self.assertIn("Reload the page and try again", page)
        self.assertNotIn("CSRF verification failed", page)

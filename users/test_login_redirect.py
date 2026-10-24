"""After signing in, ?next= leads only to a page of this site, in both editions: until
2026-10-23 any address was followed, so a link to /login/?next=https://elsewhere could send
a person who had just signed in to a page made to look like ours."""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

PASSWORD = "a long passphrase 1"


@override_settings(RATELIMIT_ENABLE=False)
class NextTest(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        User.objects.create_user("customer@example.com", "customer@example.com", PASSWORD)

    def sign_in(self, next_url):
        return self.client.post(
            f"{reverse('login')}?next={next_url}",
            {"username": "customer@example.com", "password": PASSWORD},
            HTTP_CF_CONNECTING_IP="203.0.113.5",
        )

    def test_an_address_elsewhere_leads_to_the_dashboard(self):
        for elsewhere in ("https://evil.example/", "//evil.example/", "https:evil.example"):
            with self.subTest(elsewhere):
                response = self.sign_in(elsewhere)
                self.assertEqual(response["Location"], reverse("dashboard:main"))
                self.client.logout()

    def test_a_page_of_the_site_is_followed(self):
        self.assertEqual(self.sign_in("/account/")["Location"], "/account/")

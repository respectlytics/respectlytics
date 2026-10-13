"""Who the security emails go to, and where their links point.

The community edition runs this same code on someone else's server. Its admin
alerts carry the addresses of that server's visitors, so they go to the address
its owner names and nowhere else, and every link points at that server.
"""

import re
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from users.security_emails import (
    send_account_lockout_alert,
    send_ip_banned_alert,
    send_password_changed_notification,
)

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
SITE = "https://analytics.example.com"
COMMUNITY = getattr(settings, "RESPECTLYTICS_EDITION", None) == "community"


@override_settings(CACHES=LOCMEM, SITE_URL=SITE, SECURITY_CONTACT_EMAIL="ops@example.com")
class SecurityEmailTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_admin_alerts_go_to_the_named_address_and_link_to_this_server(self):
        self.assertTrue(send_account_lockout_alert("reader@example.com", "203.0.113.7", 5))

        (message,) = mail.outbox
        self.assertEqual(message.to, ["ops@example.com"])
        self.assertIn(SITE + reverse("admin:auth_user_changelist"), message.body)

    @override_settings(SECURITY_CONTACT_EMAIL="")
    def test_without_an_address_no_admin_alert_is_sent(self):
        self.assertFalse(send_account_lockout_alert("reader@example.com", "203.0.113.7", 5))
        self.assertFalse(send_ip_banned_alert("203.0.113.7", "attack_path", "/wp-admin/"))
        self.assertEqual(mail.outbox, [])

    @override_settings(SECURITY_CONTACT_EMAIL="")
    def test_a_users_email_links_to_this_server_and_names_no_contact_it_lacks(self):
        user = User.objects.create_user("reader", "reader@example.com", "pw")

        self.assertTrue(send_password_changed_notification(user))

        (message,) = mail.outbox
        self.assertIn(f"{SITE}/password-reset/", message.body)
        self.assertNotIn("Contact us", message.body)

    @skipUnless(COMMUNITY, "community edition only")
    def test_a_community_email_points_at_nothing_but_this_server(self):
        user = User.objects.create_user("reader", "reader@example.com", "pw")
        send_password_changed_notification(user)

        (message,) = mail.outbox
        html = message.alternatives[0][0]
        hosts = set(re.findall(r"https?://[^/\s\"')]+", html + message.body))
        self.assertEqual(hosts, {SITE})

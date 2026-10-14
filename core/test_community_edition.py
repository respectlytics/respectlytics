"""What each edition tells its own users. The community edition runs on someone
else's server, so nothing in it may send people to Loheden or speak of billing it
does not have. scripts/sync_to_oss.py carries this file across, so the community
checks run in the repository they describe."""

from pathlib import Path
from unittest import skipUnless

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

COMMUNITY = getattr(settings, "RESPECTLYTICS_EDITION", None) == "community"
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def template_files():
    """Every template this project ships, in its own directories and its apps'."""
    base = Path(settings.BASE_DIR).resolve()
    roots = [Path(d) for d in settings.TEMPLATES[0]["DIRS"]]
    roots += [Path(app.path) / "templates" for app in apps.get_app_configs()]
    for root in roots:
        root = root.resolve()
        ours = root.is_relative_to(base) and "site-packages" not in root.parts
        if ours and root.is_dir():
            yield from (p for p in root.rglob("*") if p.suffix in {".html", ".txt"})


@override_settings(CACHES=LOCMEM)
class CommunityEditionTests(TestCase):
    def test_the_delete_page_speaks_of_stripe_only_where_deletion_keeps_the_customer(self):
        user = User.objects.create_user("reader", "reader@example.com", "pw")
        self.client.force_login(user)

        response = self.client.get(reverse("account_delete"))

        self.assertEqual(response.status_code, 200)
        if COMMUNITY:
            self.assertNotContains(response, "Stripe")
            self.assertNotContains(response, "payment method")
        else:
            self.assertContains(response, "Your Stripe payment history is preserved")

    @skipUnless(COMMUNITY, "community edition only")
    def test_no_template_sends_anyone_to_a_loheden_address(self):
        files = list(template_files())
        self.assertTrue(any(p.name == "500.html" for p in files))

        offenders = [str(p) for p in files if "@loheden.com" in p.read_text(encoding="utf-8")]

        self.assertEqual(offenders, [])

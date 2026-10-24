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
            self.assertContains(response, "we keep the record of the purchase for eight years")

    @skipUnless(COMMUNITY, "community edition only")
    def test_no_template_sends_anyone_to_a_loheden_address(self):
        files = list(template_files())
        self.assertTrue(any(p.name == "500.html" for p in files))

        offenders = [str(p) for p in files if "@loheden.com" in p.read_text(encoding="utf-8")]

        self.assertEqual(offenders, [])


class NoVisitCountingTests(TestCase):
    """respectlytics.com counts its own visitors with the shared analytics
    (vendor/loheden_analytics, the loheden-analytics skill); a server someone else
    runs has no business counting theirs for us, so the community edition ships
    none of it: no app, no middleware, no form fields, no dashboard."""

    @skipUnless(COMMUNITY, "the community edition only")
    def test_the_community_edition_counts_no_visits(self):
        self.assertFalse(any("loheden_analytics" in app for app in settings.INSTALLED_APPS))
        self.assertFalse(any("loheden_analytics" in m for m in settings.MIDDLEWARE))
        processors = settings.TEMPLATES[0].get("OPTIONS", {}).get("context_processors", [])
        self.assertFalse(any("loheden_analytics" in p for p in processors))
        self.assertFalse(hasattr(settings, "LOHEDEN_ANALYTICS"))
        base = Path(settings.BASE_DIR)
        self.assertFalse((base / "vendor").exists())
        carrying = [
            str(p) for p in template_files() if "analytics_fields" in p.read_text(encoding="utf-8")
        ]
        self.assertEqual(carrying, [])

    def test_the_sync_never_carries_the_counting_across(self):
        script = Path(settings.BASE_DIR) / "scripts" / "sync_to_oss.py"
        if not script.exists():
            self.skipTest("the sync script lives in the private repository")
        text = script.read_text(encoding="utf-8")
        listed = text.split("INCLUDE_DIRS = [", 1)[1].split("]", 1)[0]
        for folder in ("vendor", "website"):
            self.assertNotIn(f'"{folder}"', listed, f"{folder}/ holds the counting, never synced")


class SharedScriptsTests(TestCase):
    """The community edition's own base.html loads the scripts every dashboard page relies on,
    as respectlytics.com's does: without toast.js a failed request threw instead of saying so,
    and without the icons the scripts drew blank (found 2026-10-24)."""

    SHARED = (
        "partials/icon_templates.html",
        "js/icons.js",
        "js/toast.js",
        "js/app-shell.js",
        "{% block site_header %}",
        "{% block site_footer %}",
    )

    def test_both_bases_load_them(self):
        root = Path(settings.BASE_DIR)
        # In the edition itself, templates/base.html is its own (the override, applied)
        bases = [
            b
            for b in ("templates/base.html", "_oss_overrides/templates/base.html")
            if (root / b).exists()
        ]
        self.assertTrue(bases)
        for base in bases:
            text = (root / base).read_text()
            for needed in self.SHARED:
                self.assertIn(needed, text, f"{base} lacks {needed}")

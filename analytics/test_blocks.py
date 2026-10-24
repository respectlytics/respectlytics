"""The blocks, proved (loheden-security, "Client address, bans and rate limits").

Attack signals block for 12 months and renew; 404 scans block for 24 hours and longer on repeat;
a block keeps a keyed code and never the address, is deleted 30 days after it ends, never lands
on a shared or the server's own address, and never stands in the way of the health answer; two
requests at once make one block; the admin finds a block by its address and lifts it with one
click. respectaso-web's security/tests.py is the reference.
"""

import logging
from datetime import timedelta
from unittest import skipIf
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.db.models import QuerySet
from django.test import TestCase, override_settings
from django.urls import get_resolver, reverse
from django.utils import timezone

from .blocks import (
    ATTACK,
    ATTACK_BLOCK,
    AUTH,
    SCAN,
    SCAN_BLOCKS,
    address_key,
    block,
    delete_ended,
)
from .middleware import ATTACK_PATH_REGEX, SCAN_LIMIT
from .models import BlockedAddress
from .test_client_ip import HOSTED, LOCMEM

SCANNER = "198.51.100.40"
OTHER = "198.51.100.41"
OWNER = "198.51.100.42"
WORKERS = "2a06:98c0:3600::103"
PROXY = "10.244.0.7"  # the server's own proxy, which every request arrives through
PAGE = "/login/"  # a plain page both editions serve
# respectlytics.com's attack signals on its own admin; the community edition's admin is /admin.
HOSTED_ONLY = not getattr(settings, "ATTACK_SIGNAL_ADMIN_PREFIX", None)


def visitor(ip, **extra):
    return {"REMOTE_ADDR": PROXY, "HTTP_CF_CONNECTING_IP": ip, **extra}


@override_settings(TESTING=False, CACHES=LOCMEM, **HOSTED)
class Fresh(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        # Each block writes a warning to the log; a test that blocks on purpose stays quiet.
        self.enterContext(patch.object(logging.getLogger("analytics.blocks"), "disabled", True))


class AttackSignalTest(Fresh):
    def test_a_scanner_path_blocks_the_address_for_a_year(self):
        self.assertEqual(self.client.get("/wp-login.php", **visitor(SCANNER)).status_code, 403)
        row = BlockedAddress.objects.get()
        self.assertEqual(row.kind, ATTACK)
        self.assertAlmostEqual(
            row.expires_at, timezone.now() + ATTACK_BLOCK, delta=timedelta(minutes=1)
        )
        self.assertEqual(self.client.get(PAGE, **visitor(SCANNER)).status_code, 403)
        self.assertEqual(self.client.get(PAGE, **visitor(OTHER)).status_code, 200)

    def test_every_scanner_path_is_one(self):
        for path in (
            "/.env",
            "/.git/config",
            "/wp-admin/",
            "/xmlrpc.php",
            "/phpmyadmin/",
            "/.aws/credentials",
            "/cgi-bin/test",
            "/blog/index.php",
        ):
            with self.subTest(path=path):
                BlockedAddress.objects.all().delete()
                self.assertEqual(self.client.get(path, **visitor(SCANNER)).status_code, 403)
                self.assertTrue(BlockedAddress.objects.exists())

    def test_no_page_file_or_route_of_this_site_is_an_attack_path(self):
        # A year's block for a reader who followed a blog link would be the worst bug here.
        paths = {u["location"] for u in self._sitemap()}
        paths |= {f"/{r}" for r in self._routes()}
        paths |= {f"/static/{p}" for p in self._static_files()}
        self.assertEqual(sorted(p for p in paths if ATTACK_PATH_REGEX.search(p)), [])

    def _sitemap(self):
        response = self.client.get("/sitemap.xml", **visitor(OTHER))
        if response.status_code != 200:
            return []
        import re

        return [
            {"location": re.sub(r"^https?://[^/]+", "", u)}
            for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", response.content.decode())
        ]

    def _routes(self):
        def walk(resolver, prefix=""):
            for pattern in resolver.url_patterns:
                text = prefix + str(pattern.pattern).lstrip("^").replace("\\", "")
                if hasattr(pattern, "url_patterns"):
                    yield from walk(pattern, text)
                else:
                    yield text.rstrip("$")

        return set(walk(get_resolver()))

    def _static_files(self):
        found = set()
        for finder in finders.get_finders():
            for path, _storage in finder.list([]):
                found.add(path)
        return found

    @skipIf(HOSTED_ONLY, "respectlytics.com only: the community edition's admin is /admin")
    def test_a_post_to_admin_blocks_but_a_visit_does_not(self):
        self.assertEqual(self.client.get("/admin/", **visitor(SCANNER)).status_code, 404)
        self.assertFalse(BlockedAddress.objects.exists())
        self.assertEqual(self.client.post("/admin/login/", **visitor(SCANNER)).status_code, 403)
        self.assertEqual(BlockedAddress.objects.get().kind, ATTACK)

    @skipIf(HOSTED_ONLY, "respectlytics.com only: a self-hosted copy may have an admin account")
    def test_a_login_as_admin_blocks_and_the_owners_name_does_not(self):
        # The customer login takes an email address only; scanners try names on the admin's.
        login = reverse("admin:login")
        self.client.post(login, {"username": "someone", "password": "wrong"}, **visitor(OTHER))
        self.assertFalse(BlockedAddress.objects.exists())
        self.client.post(login, {"username": "Admin", "password": "x"}, **visitor(SCANNER))
        self.assertEqual(BlockedAddress.objects.get().kind, ATTACK)

    def test_two_requests_that_arrive_together_make_one_block_and_no_error(self):
        # Two workers each look for a block before either has filed one, and the second files
        # it too (respectaso.com, 2026-10-15: that insert failed, answered 500, mailed the owner).
        block(SCANNER, ATTACK, "the other worker")
        first = QuerySet.first

        def too_early(queryset):
            return None if queryset.model is BlockedAddress else first(queryset)

        with patch.object(QuerySet, "first", too_early):
            self.assertEqual(self.client.get("/.git/config", **visitor(SCANNER)).status_code, 403)
        self.assertEqual(BlockedAddress.objects.count(), 1)

    def test_trying_again_renews_the_year(self):
        block(SCANNER, ATTACK, "first")
        BlockedAddress.objects.update(expires_at=timezone.now() + timedelta(days=10))
        block(SCANNER, ATTACK, "again")
        row = BlockedAddress.objects.get()
        self.assertEqual(row.times, 2)
        self.assertAlmostEqual(
            row.expires_at, timezone.now() + ATTACK_BLOCK, delta=timedelta(minutes=1)
        )

    def test_an_attack_outranks_an_earlier_shorter_block(self):
        block(SCANNER, AUTH, "API keys")
        block(SCANNER, ATTACK, "then a scanner path")
        self.assertEqual(BlockedAddress.objects.get().kind, ATTACK)

    def test_the_address_every_worker_shares_is_refused_but_never_blocked(self):
        self.assertEqual(self.client.get("/.env", **visitor(WORKERS)).status_code, 403)
        self.assertFalse(BlockedAddress.objects.exists())
        self.assertEqual(self.client.get(PAGE, **visitor(WORKERS)).status_code, 200)

    def test_the_servers_own_checks_are_never_blocked(self):
        # The deploy's page check runs inside the container, from loopback.
        self.assertEqual(self.client.get("/.env", REMOTE_ADDR="127.0.0.1").status_code, 403)
        self.assertFalse(BlockedAddress.objects.exists())
        self.assertEqual(self.client.get(PAGE, REMOTE_ADDR="127.0.0.1").status_code, 200)

    def test_a_blocked_address_still_gets_the_health_answer(self):
        block(SCANNER, ATTACK, "test")
        self.assertEqual(self.client.get(PAGE, **visitor(SCANNER)).status_code, 403)
        self.assertEqual(self.client.get("/healthz", **visitor(SCANNER)).status_code, 200)


class ScanTest(Fresh):
    def scan(self, ip=SCANNER, paths=SCAN_LIMIT, **extra):
        for n in range(paths):
            self.client.get(f"/no-such-page-{n}/", **visitor(ip, **extra))

    def test_twenty_different_missing_pages_block_for_a_day(self):
        self.scan(paths=SCAN_LIMIT - 1)
        self.assertFalse(BlockedAddress.objects.exists())
        self.client.get("/one-more-missing/", **visitor(SCANNER))
        row = BlockedAddress.objects.get()
        self.assertEqual(row.kind, SCAN)
        self.assertAlmostEqual(
            row.expires_at, timezone.now() + SCAN_BLOCKS[0], delta=timedelta(minutes=1)
        )

    def test_the_same_missing_page_again_and_again_is_no_scan(self):
        for _ in range(40):
            self.client.get("/an-old-link/", **visitor(SCANNER))
        self.assertFalse(BlockedAddress.objects.exists())

    def test_a_returning_scanner_is_blocked_longer_each_time(self):
        for expected in (*SCAN_BLOCKS, SCAN_BLOCKS[-1]):
            BlockedAddress.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
            self.scan()
            row = BlockedAddress.objects.get()
            self.assertAlmostEqual(
                row.expires_at, timezone.now() + expected, delta=timedelta(minutes=1)
            )

    def test_search_and_answer_engines_are_never_blocked_for_dead_links(self):
        self.scan(HTTP_USER_AGENT="Mozilla/5.0 (compatible; Googlebot/2.1)")
        self.scan(ip=OTHER, HTTP_USER_AGENT="Mozilla/5.0 (compatible; ClaudeBot/1.0)")
        self.assertFalse(BlockedAddress.objects.exists())

    def test_missing_files_and_dashboard_pages_are_no_scan(self):
        for n in range(SCAN_LIMIT + 1):
            self.client.get(f"/static/images/missing-{n}.png", **visitor(SCANNER))
        self.assertFalse(BlockedAddress.objects.exists())

    def test_the_count_is_shared_by_every_worker(self):
        # Two gunicorn workers: a count in one process's memory would need twice the pages.
        from core import settings as site_settings

        self.assertEqual(
            site_settings.CACHES["default"]["BACKEND"],
            "django.core.cache.backends.db.DatabaseCache",
        )


class NoAddressKeptTest(Fresh):
    def test_a_block_and_its_counts_keep_a_keyed_code_and_never_the_address(self):
        self.client.get("/no-such-page/", **visitor(SCANNER))
        self.client.get("/.env", **visitor(SCANNER))
        row = BlockedAddress.objects.values().get()
        self.assertEqual(row["key"], address_key(SCANNER))
        self.assertNotIn(SCANNER, str(row))
        self.assertIsNone(cache.get(f"missing:{SCANNER}"))

    def test_a_block_is_deleted_30_days_after_it_ends(self):
        block(SCANNER, SCAN, "old")
        block(OTHER, SCAN, "recent")
        BlockedAddress.objects.filter(key=address_key(SCANNER)).update(
            expires_at=timezone.now() - timedelta(days=31)
        )
        BlockedAddress.objects.filter(key=address_key(OTHER)).update(
            expires_at=timezone.now() - timedelta(days=29)
        )
        self.assertEqual(delete_ended(), 1)
        self.assertEqual(
            list(BlockedAddress.objects.values_list("key", flat=True)), [address_key(OTHER)]
        )


class AdminTest(Fresh):
    def setUp(self):
        super().setUp()
        owner = User.objects.create_superuser("owner", "owner@example.com", "a long passphrase")
        self.client.force_login(owner)
        block(SCANNER, ATTACK, "GET /.env")
        block(OTHER, SCAN, "20 missing pages within 5 minutes")
        self.url = reverse("admin:analytics_blockedaddress_changelist")

    def otp_verified(self):
        # The admin asks for a second factor (django-otp); the test passes it as verified.
        return patch("django_otp.admin.OTPAdminSite.has_permission", return_value=True)

    def test_the_owner_finds_a_block_by_its_address(self):
        with self.otp_verified():
            page = self.client.get(self.url, {"q": SCANNER}, **visitor(OWNER))
        self.assertContains(page, "GET /.env")
        self.assertNotContains(page, "20 missing pages")

    def test_one_click_lifts_a_block(self):
        row = BlockedAddress.objects.get(key=address_key(SCANNER))
        with self.otp_verified():
            response = self.client.post(
                self.url,
                {"action": "lift_blocks", "_selected_action": [row.pk]},
                follow=True,
                **visitor(OWNER),
            )
        self.assertContains(response, "Lifted 1 block.")
        self.assertFalse(BlockedAddress.objects.filter(pk=row.pk).exists())
        self.client.logout()
        self.assertEqual(self.client.get(PAGE, **visitor(SCANNER)).status_code, 200)

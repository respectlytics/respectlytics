"""Whose address a request carries, and who the blocks can land on.

The blocks in analytics/blocks.py shut every page and the whole API, an attack
signal's for a year, so they must land on the visitor and on nobody else: not on
an address a client wrote into a header, and not on an address many people share.
"""

from unittest import skipIf

from django.conf import settings
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from analytics.client_ip import get_client_ip
from analytics.middleware import SCAN_LIMIT

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# What respectlytics.com trusts: Cloudflare's header, and nothing a client could
# write. The tests name it themselves because they also run in the community
# edition, whose settings trust no header by default.
HOSTED = {"TRUSTED_CLIENT_IP_HEADERS": ("HTTP_CF_CONNECTING_IP",), "READ_X_FORWARDED_FOR": False}
# The community edition's defaults: no header trusted, and the address a proxy of
# the server's own appended to X-Forwarded-For read from the right.
SELF_HOSTED = {"TRUSTED_CLIENT_IP_HEADERS": (), "READ_X_FORWARDED_FOR": True}
COMMUNITY = getattr(settings, "RESPECTLYTICS_EDITION", None) == "community"

# Cloudflare sends every Worker, on every account, from this one address.
CLOUDFLARE_WORKERS = "2a06:98c0:3600::103"
GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


class EditionSettingsTests(SimpleTestCase):
    @skipIf(COMMUNITY, "respectlytics.com only")
    def test_respectlytics_com_trusts_cloudflares_header_alone(self):
        self.assertEqual(settings.TRUSTED_CLIENT_IP_HEADERS, HOSTED["TRUSTED_CLIENT_IP_HEADERS"])
        self.assertIs(settings.READ_X_FORWARDED_FOR, False)

    @skipIf(not COMMUNITY, "community edition only")
    def test_a_self_hosted_server_trusts_no_header_unless_its_owner_names_one(self):
        self.assertEqual(settings.TRUSTED_CLIENT_IP_HEADERS, ())
        self.assertIs(getattr(settings, "READ_X_FORWARDED_FOR", True), True)

    def test_the_rate_limits_key_on_the_same_address(self):
        self.assertEqual(settings.RATELIMIT_IP_META_KEY, "analytics.client_ip.get_client_ip")


@override_settings(**HOSTED)
class HostedClientIpTests(SimpleTestCase):
    """respectlytics.com, reached only through Cloudflare's tunnel."""

    def ip(self, **meta):
        return get_client_ip(RequestFactory().get("/", **meta))

    def test_the_address_cloudflare_names_is_the_visitor(self):
        self.assertEqual(
            self.ip(
                REMOTE_ADDR="10.244.0.7",
                HTTP_CF_CONNECTING_IP="203.0.113.7",
                HTTP_X_FORWARDED_FOR="10.244.0.9",
            ),
            "203.0.113.7",
        )
        self.assertEqual(
            self.ip(REMOTE_ADDR="10.244.0.7", HTTP_CF_CONNECTING_IP="2001:db8::7"), "2001:db8::7"
        )

    def test_cloudflare_outranks_a_do_connecting_ip_a_client_could_have_written(self):
        """Cloudflare documents that it overwrites CF-Connecting-IP; DigitalOcean
        does not say the same of do-connecting-ip."""
        self.assertEqual(
            self.ip(
                REMOTE_ADDR="10.244.0.7",
                HTTP_CF_CONNECTING_IP="203.0.113.7",
                HTTP_DO_CONNECTING_IP="198.51.100.1",
            ),
            "203.0.113.7",
        )

    def test_a_forged_forwarded_for_changes_nothing(self):
        self.assertEqual(
            self.ip(
                REMOTE_ADDR="10.244.0.7",
                HTTP_CF_CONNECTING_IP="203.0.113.7",
                HTTP_X_FORWARDED_FOR="198.51.100.1, 10.244.0.9",
            ),
            "203.0.113.7",
        )

    def test_without_cloudflares_header_no_header_a_client_writes_names_anyone(self):
        """A ban must land on the visitor, so without CF-Connecting-IP the answer
        is the connection itself, never the do-connecting-ip or X-Forwarded-For
        a client could have sent."""
        self.assertEqual(
            self.ip(
                REMOTE_ADDR="10.244.0.7",
                HTTP_DO_CONNECTING_IP="198.51.100.1",
                HTTP_X_FORWARDED_FOR="198.51.100.2, 10.244.0.9",
            ),
            "10.244.0.7",
        )

    def test_a_header_that_is_not_an_address_is_ignored(self):
        self.assertEqual(
            self.ip(
                REMOTE_ADDR="10.244.0.7",
                HTTP_CF_CONNECTING_IP="not-an-ip",
                HTTP_DO_CONNECTING_IP="203.0.113.7",
                HTTP_X_FORWARDED_FOR="203.0.113.8",
            ),
            "10.244.0.7",
        )


@override_settings(**SELF_HOSTED)
class SelfHostedClientIpTests(SimpleTestCase):
    """The open-source edition, run by its owner directly or behind their own proxy."""

    def ip(self, **meta):
        return get_client_ip(RequestFactory().get("/", **meta))

    def test_published_directly_the_connection_is_the_visitor(self):
        self.assertEqual(
            self.ip(REMOTE_ADDR="203.0.113.7", HTTP_X_FORWARDED_FOR="198.51.100.1"), "203.0.113.7"
        )

    def test_behind_nginx_the_address_nginx_saw_is_the_visitor(self):
        """nginx appends what it saw ($proxy_add_x_forwarded_for), so a client can
        only write to the left of it."""
        self.assertEqual(
            self.ip(REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="198.51.100.1, 203.0.113.7"),
            "203.0.113.7",
        )

    def test_behind_two_proxies_on_a_private_network(self):
        self.assertEqual(
            self.ip(
                REMOTE_ADDR="172.18.0.3",
                HTTP_X_FORWARDED_FOR="198.51.100.1, 203.0.113.7, 172.18.0.2",
            ),
            "203.0.113.7",
        )

    def test_an_edge_header_means_nothing_without_the_edge(self):
        self.assertEqual(
            self.ip(
                REMOTE_ADDR="203.0.113.7",
                HTTP_CF_CONNECTING_IP="198.51.100.1",
                HTTP_DO_CONNECTING_IP="198.51.100.2",
            ),
            "203.0.113.7",
        )

    def test_running_locally_is_still_localhost(self):
        self.assertEqual(self.ip(REMOTE_ADDR="127.0.0.1"), "127.0.0.1")


@override_settings(TESTING=False, CACHES=LOCMEM, **HOSTED)
class BansLandOnTheVisitorTests(TestCase):
    """The site-wide ban, driven through the middleware as a scanner would."""

    APP_PLATFORM = "10.244.0.7"  # the proxy in front of the app: Caddy on the server
    PAGE = "/login/"  # a plain page both editions serve

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def get(self, path, visitor, **extra):
        return self.client.get(
            path, REMOTE_ADDR=self.APP_PLATFORM, HTTP_CF_CONNECTING_IP=visitor, **extra
        )

    def probe(self, visitor, **extra):
        """One attack signal blocks at once."""
        return self.get("/wp-admin/setup-config.php", visitor, **extra)

    def test_a_scanner_is_banned_from_the_whole_site(self):
        self.probe("203.0.113.7")

        self.assertEqual(self.get(self.PAGE, "203.0.113.7").status_code, 403)
        self.assertEqual(self.get(self.PAGE, "203.0.113.8").status_code, 200)

    def test_a_forged_forwarded_for_cannot_get_someone_else_banned(self):
        self.probe("203.0.113.7", HTTP_X_FORWARDED_FOR="198.51.100.1")

        self.assertEqual(self.get(self.PAGE, "198.51.100.1").status_code, 200)

    def test_without_cloudflares_header_a_forged_header_cannot_get_someone_else_banned(self):
        for _ in range(3):
            self.client.get(
                "/wp-admin/setup-config.php",
                REMOTE_ADDR=self.APP_PLATFORM,
                HTTP_DO_CONNECTING_IP="198.51.100.1",
                HTTP_X_FORWARDED_FOR="198.51.100.1",
            )

        self.assertEqual(self.get(self.PAGE, "198.51.100.1").status_code, 200)

    def test_a_forged_forwarded_for_cannot_dodge_a_ban(self):
        self.probe("203.0.113.7")

        self.assertEqual(
            self.get(self.PAGE, "203.0.113.7", HTTP_X_FORWARDED_FOR="198.51.100.9").status_code, 403
        )

    def test_many_missing_pages_ban_an_address(self):
        for n in range(SCAN_LIMIT):
            self.get(f"/no-such-page-{n}/", "203.0.113.7")

        self.assertEqual(self.get(self.PAGE, "203.0.113.7").status_code, 403)

    def test_a_search_or_ai_crawler_following_dead_links_is_never_banned(self):
        for agent in (
            GOOGLEBOT,
            "Mozilla/5.0 (compatible; GPTBot/1.2; +https://openai.com/gptbot)",
        ):
            for n in range(SCAN_LIMIT + 2):
                self.get(f"/no-such-page-{n}/", "203.0.113.7", HTTP_USER_AGENT=agent)

        self.assertEqual(self.get(self.PAGE, "203.0.113.7").status_code, 200)

    def test_a_crawlers_name_does_not_excuse_attack_probes(self):
        self.probe("203.0.113.7", HTTP_USER_AGENT=GOOGLEBOT)

        self.assertEqual(self.get(self.PAGE, "203.0.113.7").status_code, 403)

    def test_a_lifted_ban_starts_the_count_again(self):
        """Lifting a block in the admin also forgets the missing pages counted toward a
        scan, or the next one would block the address again at once."""
        from analytics.security_dashboard import unban_ip

        for n in range(SCAN_LIMIT):
            self.get(f"/no-such-page-{n}/", "203.0.113.7")
        self.assertTrue(unban_ip("203.0.113.7"))

        self.assertEqual(self.get("/no-such-page-0/", "203.0.113.7").status_code, 404)
        self.assertEqual(self.get(self.PAGE, "203.0.113.7").status_code, 200)

    def test_a_scanner_on_cloudflare_workers_cannot_ban_every_worker(self):
        """On 2026-10-13 a WordPress scanner on Workers got this address banned at
        loheden.com, and with it the uptime watchdog, which reported the site down.
        Here it would also shut out every customer who sends events from a Worker."""
        self.assertEqual(self.probe(CLOUDFLARE_WORKERS).status_code, 403)

        self.assertEqual(self.get(self.PAGE, CLOUDFLARE_WORKERS).status_code, 200)

    def test_failed_api_keys_from_cloudflare_workers_cannot_ban_every_worker(self):
        for _ in range(10):
            response = self.client.post(
                reverse("analytics:event-create"),
                {"event_name": "x"},
                REMOTE_ADDR=self.APP_PLATFORM,
                HTTP_CF_CONNECTING_IP=CLOUDFLARE_WORKERS,
                HTTP_X_APP_KEY="00000000-0000-0000-0000-000000000000",
            )
            self.assertEqual(response.status_code, 401)

        self.assertEqual(self.get(self.PAGE, CLOUDFLARE_WORKERS).status_code, 200)

    def test_a_ban_never_makes_the_service_look_down(self):
        self.probe("203.0.113.7")

        self.assertEqual(
            self.get(reverse("analytics:health-check"), "203.0.113.7").status_code, 200
        )


class EventsAreGeolocatedToTheSenderTests(TestCase):
    """An event without a country gets the sender's, looked up in the local GeoIP
    file and then dropped. A forged header must not move it to another country."""

    def setUp(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest import mock

        from analytics import geolocation
        from analytics.test_geoip import country, write_mmdb

        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        networks = {"89.160.20.0/24": country("SE"), "81.2.69.0/24": country("GB")}
        database = write_mmdb(Path(folder.name) / "dbip.mmdb", networks, "DBIP-Country-Lite")
        for name, path in (("DBIP_FILE", database), ("MAXMIND_FILE", Path(folder.name) / "no")):
            patcher = mock.patch.object(geolocation, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)

        from django.contrib.auth.models import User

        from analytics.models import App, Event

        self.Event = Event
        user = User.objects.create_user(username="geo", password="geo-pass-123")
        self.app_key = str(App.objects.create(name="Geo App", user=user).id)

    def country(self, **meta):
        response = self.client.post(
            reverse("analytics:event-create"),
            {"event_name": "opened"},
            content_type="application/json",
            HTTP_X_APP_KEY=self.app_key,
            **meta,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return self.Event.objects.get(id=response.json()["id"]).country

    @override_settings(**HOSTED)
    def test_on_app_platform_the_country_is_the_senders(self):
        self.assertEqual(
            self.country(
                REMOTE_ADDR="10.244.0.7",
                HTTP_CF_CONNECTING_IP="89.160.20.112",
                HTTP_X_FORWARDED_FOR="81.2.69.142, 10.244.0.9",
            ),
            "SE",
        )

    @override_settings(**SELF_HOSTED)
    def test_behind_a_self_hosters_nginx_the_country_is_the_senders(self):
        self.assertEqual(
            self.country(
                REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="81.2.69.142, 89.160.20.112"
            ),
            "SE",
        )


class BannedAddressesAreListedTests(TestCase):
    """The staff security dashboard lists every block, IPv6 included."""

    def test_an_ipv6_block_is_filed_under_its_whole_address(self):
        from analytics.blocks import SCAN, address_key, block
        from analytics.security_dashboard import get_banned_ips

        block("2001:db8::7", SCAN, "test")

        self.assertEqual([row["key"] for row in get_banned_ips()], [address_key("2001:db8::7")])

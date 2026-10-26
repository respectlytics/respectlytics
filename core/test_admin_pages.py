"""Every page and link of the admin opens for the owner.

One column that raises turns a whole list into a 500: on 2026-10-25 the user list did, because
its sign-in column called format_html() with nothing to format, which Django 6 refuses. So the
owner signs in with a second factor, every model the admin lists gets a row, and the admin is
walked from each of its pages that takes no argument. Every link is opened, and the links of
every page without a query are followed in turn: each list with its sort and filter links, each
row with its history and delete pages, each add page and the admin's own pages. A link that
leaves the admin (the site, the API reference) is opened and not walked.

scripts/sync_to_oss.py carries this file across, so the community edition walks its own admin
here. respectlytics.com walks its admin in website/test_admin_pages.py, which adds a row for each
model only it has."""

import ast
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from unittest import skipUnless
from urllib.parse import urldefrag, urljoin, urlsplit

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, URLPattern, resolve, reverse
from django.utils import timezone

COMMUNITY = getattr(settings, "RESPECTLYTICS_EDITION", None) == "community"
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# The admin's own URLs that are no page: logout takes a POST, autocomplete a widget's query.
NOT_PAGES = {"logout", "autocomplete"}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href")
        if tag == "a" and href:
            self.hrefs.append(href)


def links(page_url, html):
    """Every link on the page that stays on this site, as a path with its query."""
    parser = Links()
    parser.feed(html)
    ours = ("", "testserver", *settings.ALLOWED_HOSTS)
    for href in parser.hrefs:
        url = urlsplit(urldefrag(urljoin(page_url, href)).url)
        if url.scheme in ("", "http", "https") and url.netloc in ours:
            if not url.path.startswith(settings.STATIC_URL):
                yield url.path + (f"?{url.query}" if url.query else "")


def own_pages(site):
    """Each of the admin's own pages that takes no argument, and every model's list. An add
    page is reached by its link, which the admin shows only where adding is allowed."""
    for pattern in site.get_urls():
        if isinstance(pattern, URLPattern) and pattern.name and pattern.name not in NOT_PAGES:
            try:
                yield reverse(f"{site.name}:{pattern.name}")
            except NoReverseMatch:
                continue
    for model in site._registry:
        yield reverse(f"{site.name}:{model._meta.app_label}_{model._meta.model_name}_changelist")


class AdminWalk:
    """The walk, for a TestCase whose seed() makes a row of every model its admin lists."""

    maxDiff = None

    def seed(self, owner, customer):
        """A row for each model both editions' admins list; returns the customer's app."""
        from analytics.blocks import ATTACK, block
        from analytics.models import App, Event, SecretKey

        Group.objects.create(name="Support")
        app = App.objects.create(name="Recipe Box", user=customer)
        Event.objects.create(
            app=app,
            event_name="purchase",
            session_id="s1",
            timestamp=timezone.now(),
            country="SE",
            platform="iOS",
        )
        SecretKey.make(customer)
        block("198.51.100.7", ATTACK, "a scanner path")
        if apps.is_installed("django_otp.plugins.otp_static"):
            from django_otp.plugins.otp_static.models import StaticDevice

            StaticDevice.objects.create(user=owner, name="backup").token_set.create(token="a1b2c3")
        return app

    def setUp(self):
        self.owner = User.objects.create_superuser(
            "owner", "owner@example.com", "a long passphrase"
        )
        customer = User.objects.create_user("customer", "customer@example.com", "a long passphrase")
        self.seed(self.owner, customer)
        self.client.force_login(self.owner)
        if apps.is_installed("django_otp.plugins.otp_totp"):
            from django_otp import DEVICE_ID_SESSION_KEY
            from django_otp.plugins.otp_totp.models import TOTPDevice

            device = TOTPDevice.objects.create(user=self.owner, name="phone", confirmed=True)
            session = self.client.session
            session[DEVICE_ID_SESSION_KEY] = device.persistent_id
            session.save()
        self.index = reverse("admin:index")
        self.site = resolve(self.index).func.admin_site

    def test_every_model_the_admin_lists_has_a_row_here(self):
        # Without one, its list shows no row and its row pages are never opened.
        empty = [m._meta.label for m in self.site._registry if not m._default_manager.exists()]
        self.assertEqual(empty, [])

    def test_every_page_and_link_of_the_admin_opens(self):
        login = reverse("admin:login")
        queue = deque({url: (url, "the admin's URLs") for url in own_pages(self.site)}.values())
        seen, broken, opened = {url for url, _ in queue}, {}, 0
        while queue:
            url, found_on = queue.popleft()
            try:
                response = self.client.get(url)
            except Exception as error:  # the view raised: what the owner gets as a 500
                broken[url] = f"{type(error).__name__}: {error} (linked from {found_on})"
                continue
            opened += 1
            if response.status_code in (301, 302):
                if urlsplit(response["Location"]).path == login:
                    broken[url] = f"sent the signed-in owner to sign in (linked from {found_on})"
                    continue
                found = links(url, f'<a href="{response["Location"]}">')
            elif response.status_code != 200:
                broken[url] = f"{response.status_code} (linked from {found_on})"
                continue
            elif (
                url.startswith(self.index) and "?" not in url and "html" in response["Content-Type"]
            ):
                found = links(url, response.content.decode())
            else:
                continue
            for link in found:
                if link not in seen:
                    seen.add(link)
                    queue.append((link, url))
        self.assertEqual(broken, {})
        lists = {
            reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")
            for model in self.site._registry
        }
        self.assertEqual(lists - seen, set())
        self.assertGreater(opened, 100)


@skipUnless(COMMUNITY, "respectlytics.com walks its admin in website/test_admin_pages.py")
@override_settings(CACHES=LOCMEM)
class AdminPagesTest(AdminWalk, TestCase):
    pass


class FormatHtmlTest(SimpleTestCase):
    def test_nothing_calls_format_html_with_nothing_to_format(self):
        # Django 6 raises TypeError on format_html() without arguments, wherever it runs: fixed
        # HTML is mark_safe(). The walk finds it in the admin; this finds it anywhere.
        base = Path(settings.BASE_DIR)
        calls = []
        for path in base.rglob("*.py"):
            if {"venv", ".venv", "node_modules"} & set(path.relative_to(base).parts):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and not node.keywords and len(node.args) < 2:
                    func = node.func
                    if getattr(func, "attr", getattr(func, "id", None)) == "format_html":
                        calls.append(f"{path.relative_to(base)}:{node.lineno}")
        self.assertEqual(calls, [])

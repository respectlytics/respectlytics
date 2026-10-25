"""The signed-in frame (templates/app_base.html, partials/app_bar.html, dashboard_base.html):
every signed-in page has the app's own top bar and no website footer, the app switcher lists
the apps the person may open, the account menu holds every account page, and an app's views
are one list with no floating button. A page a visitor sees without signing in (the demo, a
share link) keeps the website's bar."""

import re
from unittest import skipUnless

from django.apps import apps
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase

from analytics.models import App

HOSTED = apps.is_installed("teams") and apps.is_installed("billing")


@skipUnless(HOSTED, "respectlytics.com's frame: the community edition has its own bar")
class AppShellTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="owner", email="owner@example.com", password="pw-123456"
        )
        self.app = App.objects.create(name="Recipe Box", user=self.user)
        App.objects.create(name="Atlas", user=self.user)
        self.client.force_login(self.user)

    def page(self, url):
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200, url)
        return response.content.decode()

    def test_every_signed_in_page_has_the_app_bar_and_no_website_footer(self):
        for url in (
            "/dashboard/",
            f"/dashboard/stats/{self.app.slug}/",
            f"/dashboard/funnel/{self.app.slug}/",
            f"/dashboard/apps/{self.app.slug}/settings/",
            "/account/profile/",
            "/account/team/",
            "/billing/manage/",
        ):
            html = self.page(url)
            self.assertIn('aria-controls="accountMenu"', html, url)
            self.assertIn("Respectlytics, your apps", html, url)
            self.assertNotIn("<footer", html, url)
            self.assertNotIn('id="mobile-menu-btn"', html, url)  # the website's menu
            self.assertNotIn("toggleSidebar()", html, url)  # no second menu, no floating button

    def test_the_account_menu(self):
        html = self.page("/dashboard/")
        menu = html[html.index('id="accountMenu"') :]
        for href, label in (
            ("/account/profile/", "Account settings"),
            ("/billing/manage/", "Plan and billing"),
            ("/account/team/", "Team"),
            ("/account/api-keys/", "Secret keys"),
        ):
            # each with its icon, so a row reads as a place to go
            self.assertRegex(
                menu, rf'href="{href}" class="menu-item"><svg[^>]*>.*?</svg>\s*{label}</a>'
            )
        self.assertRegex(menu, r"</svg>\s*Sign out</a>")
        self.assertIn("owner@example.com", menu)

    def test_the_docs_are_one_click_from_every_signed_in_page(self):
        settings = f"/dashboard/apps/{self.app.slug}/settings/"
        for url in ("/dashboard/", settings, "/account/api-keys/"):
            html = self.page(url)
            docs = html[html.index('id="docsMenu"') : html.index('id="accountMenu"')]
            self.assertIn('href="/sdk/"', docs, url)
            self.assertIn('href="/api/v1/reference/"', docs, url)

    def test_every_account_and_app_page_leads_back_to_the_apps(self):
        """Until 2026-10-25 only the logo led back to the app list (owner, 2026-10-25)."""
        back = re.compile(r'<a href="/dashboard/" class="[^"]*"><svg[^>]*>.*?</svg>\s*All apps</a>')
        for url in (
            "/account/profile/",
            "/account/billing/",
            "/account/api-keys/",
            f"/dashboard/stats/{self.app.slug}/",
            f"/dashboard/apps/{self.app.slug}/settings/",
        ):
            self.assertRegex(self.page(url), back, url)

    def test_the_app_switcher_lists_every_app_on_an_apps_pages_only(self):
        html = self.page(f"/dashboard/stats/{self.app.slug}/")
        self.assertIn('aria-controls="appMenu"', html)
        menu = html[html.index('id="appMenu"') :]
        self.assertLess(menu.index("Atlas"), menu.index("Recipe Box"))  # by name
        self.assertIn('aria-current="page"', html)
        self.assertNotIn('aria-controls="appMenu"', self.page("/account/profile/"))
        other = User.objects.create_user(username="x", email="x@example.com", password="pw-1234567")
        stranger = App.objects.create(name="Not yours", user=other)
        self.assertNotIn("Not yours", self.page(f"/dashboard/stats/{self.app.slug}/"))
        self.assertNotIn(stranger.slug, self.page(f"/dashboard/stats/{self.app.slug}/"))

    def test_upgrade_is_not_offered_on_the_plan_page(self):
        self.assertNotIn(">Upgrade</a>", self.page("/billing/manage/"))

    def test_the_views_are_one_list(self):
        html = self.page(f"/dashboard/stats/{self.app.slug}/")
        self.assertEqual(html.count('id="dashboardSidebar"'), 1)
        self.assertIn('data-tab="experiments"', html)
        self.assertRegex(html, r">\s*A/B tests\s*</button>")
        self.assertIn("Funnels", html)

    def test_the_demo_and_a_share_link_keep_the_website_bar(self):
        from teams.models import ShareLink

        token = ShareLink.create(self.app, self.user, "", None).token
        anonymous = Client()
        for url in ("/demo/", f"/share/{token}/"):
            html = anonymous.get(url).content.decode()
            self.assertNotIn('aria-controls="accountMenu"', html, url)
            self.assertIn('id="mobile-menu-btn"', html, url)
            self.assertIn("app-sidebar-public", html, url)

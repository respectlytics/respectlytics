from datetime import timedelta
from html import unescape
from unittest import skipUnless

from django.apps import apps
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from analytics.models import App, Event


class DashboardViewTestCase(TestCase):
    """Test the main dashboard page"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.client.force_login(self.user)

    def test_dashboard_renders_with_apps(self):
        App.objects.create(name="My Test App", user=self.user)
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Test App")

    def test_dashboard_renders_with_non_ascii_named_app(self):
        """
        Regression test: an app whose name slugifies to '' (e.g. Korean-only)
        used to crash /dashboard/ with NoReverseMatch on the stats link.
        """
        app = App.objects.create(name="통계앱", user=self.user)
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "통계앱")
        self.assertContains(response, f"/dashboard/stats/{app.slug}/")


HOSTED = apps.is_installed("teams") and apps.is_installed("billing")


@skipUnless(HOSTED, "respectlytics.com's app list: the community edition has its own")
class AppListTest(TestCase):
    """The app list (dashboard/dashboard.html): one card per app that opens its Overview, its
    status from one query for every app, shared apps in the same list, one quiet line about the
    plan and a card only when the plan needs something done, and a real empty state. Renaming,
    the key and deleting are on the app's Settings page (teams/tests.py)."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="owner", email="owner@example.com", password="pw-123456"
        )
        self.subscription = self.user.subscription
        self.plan(
            status="active",
            plan="pro",
            monthly_event_limit=1_000_000,
            current_period_events=12_345,
            current_period_end=timezone.now() + timedelta(days=10),
        )
        self.client.force_login(self.user)

    def plan(self, **fields):
        for field, value in fields.items():
            setattr(self.subscription, field, value)
        self.subscription.save()

    def page(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def event(self, app, minutes_ago):
        Event.objects.create(
            app=app,
            event_name="app_open",
            session_id="s" * 32,
            timestamp=timezone.now() - timedelta(minutes=minutes_ago),
        )

    def test_each_app_is_one_card_that_opens_its_overview_and_says_its_last_event(self):
        busy = App.objects.create(name="Busy", user=self.user)
        self.event(busy, 90)
        self.event(busy, 4)
        quiet = App.objects.create(name="Quiet", user=self.user)
        html = self.page()
        self.assertIn(f'href="/dashboard/stats/{busy.slug}/"', html)
        self.assertIn("Last event 4 minutes ago", html)
        self.assertIn("Waiting for the first event.", html)
        self.assertIn(f'href="/setup/?app={quiet.slug}"', html)
        self.assertEqual(html.count('class="btn-primary'), 1)  # New app, the one main action

    def test_the_key_and_the_app_actions_are_not_on_the_list(self):
        app = App.objects.create(name="Busy", user=self.user)
        html = self.page()
        self.assertNotIn(str(app.id), html)
        for gone in ("regenerate-key", "/delete/", "/update/", "Show</button>", "animation"):
            self.assertNotIn(gone, html)

    def test_the_last_events_are_one_query_however_many_apps(self):
        App.objects.create(name="One", user=self.user)
        with CaptureQueriesContext(connection) as one:
            self.page()
        for name in ("Two", "Three", "Four"):
            self.event(App.objects.create(name=name, user=self.user), 1)
        with CaptureQueriesContext(connection) as four:
            html = self.page()
        self.assertEqual(html.count("Last event 1 minute ago"), 3)
        self.assertEqual(len(four), len(one))
        reads = [q["sql"] for q in four if '"analytics_event"' in q["sql"]]
        self.assertEqual(len(reads), 1, reads)
        # One subquery per app row, by app and then the newest timestamp: Event's (app, timestamp)
        self.assertRegex(
            reads[0], r'WHERE "U0"\."app_id" = \("analytics_app"\."id"\) ORDER BY \S+ DESC LIMIT 1'
        )

    def test_shared_apps_are_in_the_same_list_after_the_persons_own(self):
        from teams.models import Membership

        owner = User.objects.create_user(username="shop", email="shop@example.com")
        owner.subscription.status, owner.subscription.plan = "active", "pro"
        owner.subscription.save()
        theirs = App.objects.create(name="Aardvark", user=owner)
        Membership.objects.create(owner=owner, member=self.user, role=Membership.VIEWER)
        mine = App.objects.create(name="Zebra", user=self.user)
        html = self.page()
        self.assertIn("Shared by shop@example.com", html)
        self.assertLess(html.index(mine.name), html.index(theirs.name))
        self.assertNotIn(f"?app={theirs.slug}", html)  # its setup is the owner's

    def test_one_quiet_line_about_the_plan_and_no_card_while_all_is_well(self):
        App.objects.create(name="Busy", user=self.user)
        html = self.page()
        self.assertIn("Pro plan, 12,345 of 1,000,000 events this month", html)
        self.assertIn('href="/billing/manage/"', html)
        self.assertNotIn('aria-label="Your plan"', html)

    def test_the_plan_card_says_what_needs_doing(self):
        App.objects.create(name="Busy", user=self.user)
        cases = [
            ({"current_period_events": 850_000}, "Close to your plan's 1,000,000 events."),
            ({"current_period_events": 1_200_000}, "Past your plan's 1,000,000 events."),
            ({"current_period_events": 2_000_000}, "Twice your plan's 1,000,000 events are used."),
            (
                {"status": "past_due", "current_period_events": 0},
                "The last payment did not go through.",
            ),
            (
                {"status": "active", "scheduled_plan": "growth"},
                "Your plan changes to Growth",
            ),
            (
                {
                    "status": "free",
                    "plan": "free",
                    "scheduled_plan": None,
                    "monthly_event_limit": 20_000,
                    "current_period_events": 17_000,
                    "billing_period": "",
                },
                "Close to this month's 20,000 free events.",
            ),
            ({"current_period_events": 20_000}, "This month's 20,000 free events are used."),
        ]
        for fields, words in cases:
            with self.subTest(words):
                self.plan(**fields)
                html = unescape(self.page())
                self.assertIn('aria-label="Your plan"', html)
                self.assertIn(words, html)

    def test_an_account_whose_apps_are_gone_sees_an_empty_state_with_the_one_action(self):
        self.plan(first_app_at=timezone.now() - timedelta(days=3))
        html = self.page()
        self.assertIn("No apps yet.", html)
        self.assertEqual(html.count('href="/setup/?new=1" class="btn-primary'), 1)

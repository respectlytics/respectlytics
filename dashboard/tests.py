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
    status and its last 14 days from two queries for every app, shared apps in the same list,
    the plan with a meter of its events and a card only when the plan needs something done, and
    a real empty state. Renaming, the key and deleting are on the app's Settings page
    (teams/tests.py)."""

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
        for gone in ("regenerate-key", "/delete/", "/update/", "Show</button>"):
            self.assertNotIn(gone, html)

    def test_the_last_events_and_the_activity_are_two_queries_however_many_apps(self):
        App.objects.create(name="Quiet", user=self.user)  # never sent one: no activity to read
        for name in ("One", "Two"):
            self.event(App.objects.create(name=name, user=self.user), 1)
        with CaptureQueriesContext(connection) as two:
            self.page()
        for name in ("Three", "Four"):
            self.event(App.objects.create(name=name, user=self.user), 1)
        with CaptureQueriesContext(connection) as four:
            html = self.page()
        self.assertEqual(html.count("Last event 1 minute ago"), 4)
        self.assertEqual(len(four), len(two))
        reads = [q["sql"] for q in four if '"analytics_event"' in q["sql"]]
        self.assertEqual(len(reads), 2, reads)
        # One subquery per app row, by app and then the newest timestamp: Event's (app, timestamp)
        self.assertRegex(
            reads[0], r'WHERE "U0"\."app_id" = \("analytics_app"\."id"\) ORDER BY \S+ DESC LIMIT 1'
        )
        # The 14 days of every app that sent an event, grouped in the database by app and day,
        # filtered by app first so the (app, timestamp) index carries it
        self.assertIn('WHERE ("analytics_event"."app_id" IN (', reads[1])
        self.assertIn("GROUP BY", reads[1])
        # and kept for five minutes: the next visit reads only the last events
        with CaptureQueriesContext(connection) as again:
            self.page()
        self.assertEqual(len([q for q in again if '"analytics_event"' in q["sql"]]), 1)

    def test_each_card_draws_its_last_14_days_and_its_week_against_the_one_before(self):
        rising = App.objects.create(name="Rising", user=self.user)
        for minutes in (5, 60 * 24 * 2, 60 * 24 * 3, 60 * 24 * 10):  # 3 this week, 1 before
            self.event(rising, minutes)
        falling = App.objects.create(name="Falling", user=self.user)
        for minutes in (60 * 24 * 9, 60 * 24 * 11, 60 * 24 * 12, 60 * 24 * 13 - 1):
            self.event(falling, minutes)
        self.event(falling, 60 * 24 * 1)  # 1 this week, 4 before
        new = App.objects.create(name="New", user=self.user)
        self.event(new, 90)  # nothing before to compare with
        html = self.page()

        def card(name):
            start = html.index(f">{name}</a>")
            return html[start : html.index("</li>", start)]

        self.assertIn(">3</span>", card("Rising"))
        self.assertIn('200%<span class="sr-only"> more than the 7 days before', card("Rising"))
        self.assertIn("live-dot-on", card("Rising"))  # an event 5 minutes ago
        self.assertIn("live-dot-off", card("Falling"))  # a day ago
        self.assertIn(">1</span>", card("Falling"))
        self.assertIn('75%<span class="sr-only"> fewer than the 7 days before', card("Falling"))
        self.assertNotIn("%<span", card("New"))
        for name in ("Rising", "Falling", "New"):
            self.assertIn('aria-label="Events each day over the last 14 days"', card(name))
            self.assertIn("events in the last 7 days", card(name))

    def test_an_apps_hue_is_its_own_and_never_changes(self):
        from dashboard.views import APP_HUES

        app = App.objects.create(name="Atlas", user=self.user)
        hue = APP_HUES[app.pk.int % len(APP_HUES)]
        self.assertIn(f'style="--app: {hue}; --i: 0"', self.page())
        App.objects.create(name="Aardvark", user=self.user)  # comes first now
        self.assertIn(f'style="--app: {hue}; --i: 1"', self.page())

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
        self.assertIn('<span class="plan-chip-paid">Pro plan</span>', html)
        self.assertIn(">12,345 of 1,000,000 events this month</span>", html)
        self.assertIn('class="block h-full rounded-full bg-brand-400" style="width: 1%"', html)
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

"""Event groups (analytics/event_groups.py): they make themselves from every name an app has sent,
the owner can overrule them, the summary carries them for the dashboard and the API alike, and a
read costs the database at most one short pass over the app's names (CLAUDE.md, Database work).
How the conversion views and the funnel read through them: conversion/test_grouped_views.py."""

import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from analytics import event_groups
from analytics.models import App, Event


class GroupsMakeThemselvesTest(TestCase):
    def groups(self, names, separate=(), own=None):
        return event_groups.groups(names, {"separate": list(separate), "own": own or {}})

    def test_names_that_start_with_the_same_word_are_one_group(self):
        found = self.groups(["purchase_light", "purchase_pro", "app_open", "screen_view"])
        self.assertEqual(found, {"purchase": ["purchase_light", "purchase_pro"]})

    def test_the_bare_word_joins_its_group_and_every_separator_counts(self):
        found = self.groups(["purchase", "purchase.pro", "purchase-light", "level:1", "level/2"])
        self.assertEqual(found["purchase"], ["purchase", "purchase-light", "purchase.pro"])
        self.assertEqual(found["level"], ["level/2", "level:1"])

    def test_steps_and_outcomes_are_not_added_up(self):
        for names in [
            ["purchase_completed", "purchase_failed"],
            ["onboarding_started", "onboarding_completed"],
            ["app_open", "app_close"],
            ["sign_up", "sign_in"],
            ["purchase", "purchase_failed"],
            ["onboarding_step_1", "onboarding_step_2"],
        ]:
            self.assertEqual(self.groups(names), {}, names)

    def test_kinds_are(self):
        found = self.groups(
            [
                "subscription_monthly",
                "subscription_annual",
                "share_twitter",
                "share_mail",
                "level_1",
                "level_2",
            ]
        )
        self.assertEqual(set(found), {"subscription", "share", "level"})

    def test_a_name_alone_or_starting_with_a_separator_is_no_group(self):
        self.assertEqual(self.groups(["purchase_pro", "_internal_a", "_internal_b"]), {})

    def test_a_group_shown_separately_stays_apart(self):
        self.assertEqual(self.groups(["app_open", "app_close"], separate=["app"]), {})

    def test_an_owners_group_comes_first_and_takes_its_events_out_of_the_others(self):
        found = self.groups(
            ["purchase_light", "purchase_pro", "purchase_gift", "pro_upgrade"],
            own={"paid": ["purchase_pro", "pro_upgrade", "never_sent"]},
        )
        self.assertEqual(
            found,
            {
                "paid": ["purchase_pro", "pro_upgrade"],
                "purchase": ["purchase_gift", "purchase_light"],
            },
        )

    def test_an_automatic_group_left_with_one_event_disappears(self):
        found = self.groups(["purchase_light", "purchase_pro"], own={"pro": ["purchase_pro", "x"]})
        self.assertEqual(found, {"pro": ["purchase_pro"]})


class ChangeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="pw")
        self.app = App.objects.create(name="Shop", user=self.user)

    def test_a_group_of_ones_own_holds_only_events_the_app_sent(self):
        known = {"buy_a", "pro_buy"}
        event_groups.change(self.app, "create", "buy", ["buy_a", "pro_buy", "made_up"], known)
        self.app.refresh_from_db()
        self.assertEqual(self.app.event_groups["own"], {"buy": ["buy_a", "pro_buy"]})
        with self.assertRaises(event_groups.Refused):
            event_groups.change(self.app, "create", "one", ["buy_a", "made_up"], known)

    def test_an_event_moved_into_a_new_group_leaves_the_old_one(self):
        known = {"a", "b", "c"}
        event_groups.change(self.app, "create", "first", ["a", "b"], known)
        event_groups.change(self.app, "create", "second", ["b", "c"], known)
        self.assertEqual(self.app.event_groups["own"], {"second": ["b", "c"]})

    def test_separate_group_again_and_remove(self):
        event_groups.change(self.app, "separate", "app", [], set())
        self.assertEqual(self.app.event_groups["separate"], ["app"])
        event_groups.change(self.app, "group_again", "app", [], set())
        self.assertEqual(self.app.event_groups["separate"], [])
        event_groups.change(self.app, "create", "x", ["a", "b"], {"a", "b"})
        event_groups.change(self.app, "remove", "x", [], set())
        self.assertEqual(self.app.event_groups["own"], {})

    def test_what_the_dashboard_does_not_ask_is_refused(self):
        for action, name in [("rename", "x"), ("separate", ""), ("separate", "x" * 256)]:
            with self.assertRaises(event_groups.Refused):
                event_groups.change(self.app, action, name, [], set())


class SummaryCarriesTheGroupsTest(APITestCase):
    URL = "/api/v1/events/summary/"

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="owner", password="pw")
        self.app = App.objects.create(name="Shop", user=self.user)
        self.client.force_login(self.user)
        self.client.credentials(HTTP_X_APP_KEY=str(self.app.id))
        now = timezone.now() - timedelta(minutes=5)
        for name, times in [("purchase_pro", 3), ("purchase_light", 2), ("app_open", 4)]:
            for _ in range(times):
                Event.objects.create(app=self.app, event_name=name, timestamp=now, country="SE")

    def test_the_summary_carries_each_group_with_its_split(self):
        data = self.client.get(self.URL).data
        self.assertEqual(
            data["event_groups"],
            [
                {
                    "name": "purchase",
                    "total": 5,
                    "automatic": True,
                    "events": [
                        {"event_name": "purchase_pro", "count": 3},
                        {"event_name": "purchase_light", "count": 2},
                    ],
                }
            ],
        )
        self.assertEqual(data["events_by_name"]["purchase_pro"], 3)  # the names stay as they were

    def test_a_change_shows_at_once_and_a_cached_summary_asks_the_events_nothing(self):
        self.client.get(self.URL)
        event_groups.change(self.app, "separate", "purchase", [], set())
        with CaptureQueriesContext(connection) as queries:
            data = self.client.get(self.URL).data
        self.assertEqual(data["event_groups"], [])
        # only the cache's freshness mark: the app's newest event, one indexed row
        on_events = [q["sql"] for q in queries if '"analytics_event"' in q["sql"]]
        self.assertEqual(len(on_events), 1, on_events)
        self.assertIn("LIMIT 1", on_events[0])

    def test_the_groups_add_one_pass_over_the_names_to_a_fresh_summary(self):
        with CaptureQueriesContext(connection) as queries:
            self.client.get(self.URL)
        on_events = [q["sql"] for q in queries if '"analytics_event"' in q["sql"]]
        # what the summary always asked: the freshness mark, then total, by name, by day,
        # countries and their count; and once per NAMES_TTL the app's names, one index probe
        # per name; the groups are worked out from "by name" in Python
        self.assertEqual(len(on_events), 7, [sql[:120] for sql in on_events])
        self.assertEqual(sum("WITH RECURSIVE names" in sql for sql in on_events), 1)
        with CaptureQueriesContext(connection) as queries:
            event_groups.known_names(self.app.id)
        self.assertFalse([q for q in queries if '"analytics_event"' in q["sql"]])

    def test_a_group_is_the_same_in_a_range_where_one_of_its_events_happened(self):
        """Groups come from every name the app has sent, never from the range on screen."""
        long_ago = timezone.now() - timedelta(days=40)
        Event.objects.filter(event_name="purchase_light").update(timestamp=long_ago)
        data = self.client.get(self.URL, {"from": timezone.now().date().isoformat()}).data
        self.assertEqual(
            data["event_groups"],
            [
                {
                    "name": "purchase",
                    "total": 3,
                    "automatic": True,
                    "events": [{"event_name": "purchase_pro", "count": 3}],
                }
            ],
        )


class DashboardChangesTheGroupsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="pw")
        self.app = App.objects.create(name="Shop", user=self.user)
        now = timezone.now()
        for name in ["buy_a", "pro_buy"]:
            Event.objects.create(app=self.app, event_name=name, timestamp=now)
        self.url = f"/dashboard/api/apps/{self.app.slug}/event-groups/"

    def post(self, body, user=None):
        self.client.force_login(user or self.user)
        return self.client.post(self.url, json.dumps(body), content_type="application/json")

    def test_a_group_of_ones_own_is_saved_with_one_small_lookup_per_event(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.post(
                {"action": "create", "name": "buy", "events": ["buy_a", "pro_buy", "nope"]}
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            {"name": "buy", "automatic": False, "events": ["buy_a", "pro_buy"]},
            response.json()["groups"],
        )
        self.app.refresh_from_db()
        self.assertEqual(self.app.event_groups["own"], {"buy": ["buy_a", "pro_buy"]})
        # one EXISTS for each chosen event and for the name, then the state it answers with
        # reads the app's names once
        lookups = [q["sql"] for q in queries if '"analytics_event"' in q["sql"]]
        exists = [sql for sql in lookups if "WITH RECURSIVE" not in sql]
        self.assertEqual(len(exists), 4)
        self.assertTrue(all("LIMIT 1" in sql for sql in exists), exists)
        self.assertEqual(len(lookups), 5)

    def test_the_panel_reads_every_group_with_every_name(self):
        Event.objects.create(app=self.app, event_name="share_mail", timestamp=timezone.now())
        Event.objects.create(app=self.app, event_name="share_sms", timestamp=timezone.now())
        self.post({"action": "create", "name": "buy", "events": ["buy_a", "pro_buy"]})
        self.client.force_login(self.user)
        cache.clear()
        data = self.client.get(self.url).json()
        self.assertEqual(
            data,
            {
                "groups": [
                    {"name": "buy", "automatic": False, "events": ["buy_a", "pro_buy"]},
                    {"name": "share", "automatic": True, "events": ["share_mail", "share_sms"]},
                ],
                "separate": [],
                "events": ["buy_a", "pro_buy", "share_mail", "share_sms"],
            },
        )
        separated = self.post({"action": "separate", "name": "share"}).json()
        self.assertEqual(separated["separate"], ["share"])
        self.assertEqual([g["name"] for g in separated["groups"]], ["buy"])

    def test_a_group_may_not_take_the_name_of_an_event_outside_it(self):
        response = self.post({"action": "create", "name": "pro_buy", "events": ["buy_a", "nope"]})
        self.assertEqual(response.status_code, 400)
        Event.objects.create(app=self.app, event_name="buy_b", timestamp=timezone.now())
        response = self.post({"action": "create", "name": "buy_a", "events": ["buy_a", "buy_b"]})
        self.assertEqual(response.status_code, 200)
        response = self.post({"action": "create", "name": "buy_a", "events": ["buy_b", "pro_buy"]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"],
            "An event already has that name. Choose another, or add that event.",
        )

    def test_a_refusal_says_why(self):
        response = self.post({"action": "create", "name": "buy", "events": ["buy_a"]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Choose at least two events for the group.")

    def test_another_persons_app_is_not_found(self):
        stranger = User.objects.create_user(username="stranger", password="pw")
        response = self.post({"action": "separate", "name": "buy"}, user=stranger)
        self.assertEqual(response.status_code, 404)
        self.app.refresh_from_db()
        self.assertEqual(self.app.event_groups, {})


class KnownNamesAndGroupingTest(TestCase):
    def setUp(self):
        cache.clear()
        user = User.objects.create_user(username="owner", password="pw")
        self.app = App.objects.create(name="Shop", user=user)
        other = App.objects.create(name="Other", user=user)
        now = timezone.now()
        for name in ["purchase_pro", "app_open", "purchase_light", "purchase_pro", "purchase"]:
            Event.objects.create(app=self.app, event_name=name, timestamp=now)
        Event.objects.create(app=other, event_name="elsewhere", timestamp=now)

    def test_every_name_the_app_sent_once_alphabetically_in_one_query(self):
        with CaptureQueriesContext(connection) as queries:
            names = event_groups.known_names(self.app.id)
        self.assertEqual(names, ["app_open", "purchase", "purchase_light", "purchase_pro"])
        self.assertEqual(len([q for q in queries if '"analytics_event"' in q["sql"]]), 1)

    def test_at_most_max_names(self):
        with mock.patch.object(event_groups, "MAX_NAMES", 2):
            self.assertEqual(event_groups.known_names(self.app.id), ["app_open", "purchase"])

    def test_grouping_reads_names_as_their_groups(self):
        grouping = event_groups.Grouping.of(self.app)
        self.assertEqual(grouping.label("purchase_pro"), "purchase")
        self.assertEqual(grouping.label("purchase"), "purchase")
        self.assertEqual(grouping.label("app_open"), "app_open")
        self.assertEqual(
            grouping.expand(["purchase", "app_open"]),
            ["purchase", "purchase_light", "purchase_pro", "app_open"],
        )
        sql, params = grouping.sql("event_name")
        self.assertTrue(sql.startswith("(CASE event_name WHEN %s THEN %s"))
        self.assertEqual(len(params), 6)
        self.assertNotEqual(grouping.key(), event_groups.NONE.key())
        self.assertEqual(event_groups.NONE.sql("event_name"), ("event_name", []))
        self.assertEqual(event_groups.NONE.expand(["purchase"]), ["purchase"])

    def test_a_change_to_the_groups_changes_the_key(self):
        before = event_groups.Grouping.of(self.app).key()
        event_groups.change(self.app, "separate", "purchase", [], set())
        self.assertEqual(event_groups.Grouping.of(self.app).key(), event_groups.NONE.key())
        self.assertNotEqual(before, event_groups.NONE.key())

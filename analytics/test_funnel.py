"""The funnel in one pass gives what the recursive query gave (2026-10-26).

The funnel reads each session's first moment at each step: a session reaches step i+1 when that
step's first moment comes after step i's, within the window when one is set. Until 2026-10-26 a
recursive query walked those first occurrences; it now reads them in one pass. This reference
reads the same random sessions in Python: steps in and out of order, repeated, missing, a name
in two steps (it belongs to the first), a group, a window, and the country and platform filters.
"""

import random
from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from analytics.models import App, Event

NAMES = ["open", "paywall", "plan_a", "plan_b", "buy", "other"]


def reference(events, step_names, window_seconds=None):
    owner = {}
    for i, names in enumerate(step_names):
        for name in names:
            owner.setdefault(name, i)
    firsts = defaultdict(dict)
    for e in events:
        if e.session_id and e.event_name in owner:
            step = owner[e.event_name]
            if step not in firsts[e.session_id] or e.timestamp < firsts[e.session_id][step]:
                firsts[e.session_id][step] = e.timestamp
    counts = [0] * len(step_names)
    for times in firsts.values():
        if 0 not in times:
            continue
        reached = 0
        for i in range(1, len(step_names)):
            before, at = times.get(i - 1), times.get(i)
            if at is None or not at > before:
                break
            if window_seconds and (at - before).total_seconds() > window_seconds:
                break
            reached = i
        for i in range(reached + 1):
            counts[i] += 1
    return counts


class FunnelMatchesItsReferenceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = User.objects.create_user(username="owner", password="pw")
        cls.app = App.objects.create(name="Lumenrest Sleep Sounds", user=user)
        rng = random.Random(26)
        start = timezone.now() - timedelta(days=3)
        events = []
        for s in range(400):
            session = "" if s % 43 == 0 else f"s{s:04d}"
            moment = start + timedelta(minutes=rng.randrange(0, 3000))
            platform, country = rng.choice(["iOS", "Android"]), rng.choice(["SE", "DE", None])
            for _ in range(rng.randrange(1, 10)):
                moment += timedelta(seconds=rng.randrange(1, 400))
                events.append(
                    Event(
                        app=cls.app,
                        event_name=rng.choice(NAMES),
                        timestamp=moment,
                        session_id=session,
                        platform=platform,
                        country=country,
                    )
                )
        Event.objects.bulk_create(events)
        cls.events = events

    def check(self, steps, step_names=None, window_minutes=None, **filters):
        params = {"steps": ",".join(steps)}
        if window_minutes:
            params["window_minutes"] = window_minutes
        params.update({k: ",".join(v) for k, v in filters.items()})
        client = APIClient()
        client.force_login(self.app.user)
        response = client.get("/api/v1/events/funnel/", params, HTTP_X_APP_KEY=str(self.app.id))
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        events = [
            e
            for e in self.events
            if all(getattr(e, field) in values for field, values in filters.items())
        ]
        want = reference(
            events,
            step_names or [[s] for s in steps],
            window_minutes * 60 if window_minutes else None,
        )
        self.assertEqual([row["count"] for row in data["funnel"]], want)
        return want

    def test_steps_in_order(self):
        counts = self.check(["open", "paywall", "buy"])
        self.assertGreater(counts[-1], 0)

    def test_two_steps_ten_steps_and_a_name_in_two_steps(self):
        self.check(["paywall", "buy"])
        self.check(["open", "buy", "open", "paywall"])
        self.check(
            [
                "open",
                "paywall",
                "plan_a",
                "plan_b",
                "buy",
                "other",
                "open",
                "paywall",
                "buy",
                "other",
            ]
        )

    def test_a_window(self):
        self.check(["open", "paywall", "buy"], window_minutes=5)

    def test_the_filters(self):
        self.check(["open", "paywall", "buy"], country=["SE"])
        self.check(["open", "buy"], platform=["iOS"])

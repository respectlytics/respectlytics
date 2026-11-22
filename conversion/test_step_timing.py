"""Step timing in SQL gives the answer the Python reading it replaced gave (2026-10-26).

`StepTimingView` loaded every event of the funnel's steps into Python and walked each session; it
now asks the database for one row. The old reading is kept here as the reference, and both read
the same random sessions: repeated steps, steps out of order, missing steps, a group standing for
two events, a name in two steps, events without a session and other apps' events.
"""

import random
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from analytics import event_groups
from analytics.models import App, Event
from conversion.views import StepTimingView

NAMES = ["open", "paywall", "plan_a", "plan_b", "buy", "other"]


def reference(events, steps, grouping):
    """The Python reading StepTimingView used until 2026-10-26, unchanged in substance."""
    step_index = {}
    for i, step in enumerate(steps):
        for name in grouping.expand([step]):
            step_index[name] = i
    sessions = {}
    for e in sorted(events, key=lambda e: (e.session_id or "", e.timestamp)):
        if e.event_name in step_index:
            sessions.setdefault(e.session_id, []).append(e)
    transition_times = {i: [] for i in range(len(steps) - 1)}
    totals, with_first, with_all = [], 0, 0
    for session_events in sessions.values():
        seen = {}
        for e in session_events:
            seen.setdefault(step_index[e.event_name], e.timestamp)
        if 0 in seen:
            with_first += 1
        complete = True
        for i in range(len(steps)):
            if i not in seen or (i > 0 and seen[i] < seen[i - 1]):
                complete = False
                break
        if complete:
            with_all += 1
            totals.append((seen[len(steps) - 1] - seen[0]).total_seconds())
        for i in range(len(steps) - 1):
            if i in seen and i + 1 in seen and seen[i + 1] >= seen[i]:
                transition_times[i].append((seen[i + 1] - seen[i]).total_seconds())

    def percentile(values, p):
        values = sorted(values)
        n = len(values)
        if n == 1:
            return values[0]
        k = (n - 1) * p / 100.0
        f = int(k)
        c = min(f + 1, n - 1)
        return values[f] if f == c else values[f] * (c - k) + values[c] * (k - f)

    def stats(values):
        if not values:
            return {"median_seconds": 0, "mean_seconds": 0, "p25_seconds": 0, "p75_seconds": 0}
        return {
            "median_seconds": round(percentile(values, 50), 2),
            "mean_seconds": round(sum(values) / len(values), 2),
            "p25_seconds": round(percentile(values, 25), 2),
            "p75_seconds": round(percentile(values, 75), 2),
        }

    transitions = [
        {
            "from": steps[i],
            "to": steps[i + 1],
            "sessions_analyzed": len(transition_times[i]),
            **stats(transition_times[i]),
        }
        for i in range(len(steps) - 1)
    ]
    summary = {
        "sessions_with_first_step": with_first,
        "sessions_with_all_steps": with_all,
        "completion_rate": round(with_all / with_first, 3) if with_first else 0,
        "median_total_seconds": round(percentile(totals, 50), 2) if totals else 0,
        "mean_total_seconds": round(sum(totals) / len(totals), 2) if totals else 0,
    }
    return {"transitions": transitions, "funnel_summary": summary}


class StepTimingMatchesReferenceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = User.objects.create_user(username="owner", password="pw")
        cls.app = App.objects.create(name="Lumenrest Sleep Sounds", user=user)
        other = App.objects.create(name="Driftnook", user=user)
        rng = random.Random(20261026)
        start = timezone.now() - timedelta(days=3)
        events = []
        for s in range(300):
            session = None if s % 37 == 0 else f"s{s:04d}"
            moment = start + timedelta(minutes=rng.randrange(0, 3000))
            for _ in range(rng.randrange(1, 9)):
                moment += timedelta(
                    seconds=rng.randrange(0, 400), microseconds=rng.randrange(10**6)
                )
                app = other if s % 29 == 0 else cls.app
                events.append(
                    Event(
                        app=app, event_name=rng.choice(NAMES), timestamp=moment, session_id=session
                    )
                )
        Event.objects.bulk_create(events)
        cls.events = [e for e in events if e.app_id == cls.app.id]

    def check(self, steps, grouping=event_groups.NONE):
        qs = Event.objects.filter(app=self.app)
        with CaptureQueriesContext(connection) as queries:
            got = StepTimingView()._calculate_step_timing(qs, steps, grouping)
        self.assertEqual(len(queries), 1)
        self.assertEqual(got, reference(self.events, steps, grouping))
        return got

    def test_plain_steps(self):
        got = self.check(["open", "paywall", "buy"])
        self.assertGreater(got["funnel_summary"]["sessions_with_all_steps"], 0)

    def test_two_steps_and_ten(self):
        self.check(["paywall", "buy"])
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

    def test_a_group_as_a_step(self):
        grouping = event_groups.Grouping({"plan": ["plan_a", "plan_b"]})
        self.check(["paywall", "plan", "buy"], grouping)

    def test_a_name_in_two_steps_counts_for_the_last(self):
        self.check(["open", "buy", "open"])

    def test_steps_nobody_sent(self):
        got = self.check(["never_sent", "nor_this"])
        self.assertEqual(got["funnel_summary"]["sessions_with_first_step"], 0)

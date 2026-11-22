"""Paths and drop-offs counted in the database give the answers the Python walks gave (2026-10-26).

`ConversionPathsView` fetched one row per converting session and then every event of the top
paths' sessions by a list of their ids; `DropOffView` fetched one row per session that did not
convert. Both now return only the rows they answer with. The old readings are kept here as the
reference and read the same random sessions: repeated events, a group, events without a session,
other apps' events and a conversion that is not a session's last event.
"""

import random
from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from analytics import event_groups
from analytics.base_events import slices_in
from analytics.models import App, Event
from conversion.views import ConversionPathsView, DropOffView, EventCorrelationView

NAMES = ["open", "browse", "browse", "paywall", "plan_a", "plan_b", "buy", "share"]
GOAL = ["buy"]


def sessions_of(events):
    sessions = defaultdict(list)
    for e in sorted(events, key=lambda e: e.timestamp):
        if e.session_id:
            sessions[e.session_id].append(e)
    return sessions


def reference_paths(events, conversion, max_length, min_sessions, limit, grouping):
    """What ConversionPathsView answered until 2026-10-26, keyed by path."""
    sessions = sessions_of(events)
    total = len(sessions)
    walks = defaultdict(list)
    for session in sessions.values():
        if not any(e.event_name in conversion for e in session):
            continue
        steps = []
        for e in session:
            name = grouping.label(e.event_name)
            if not steps or steps[-1][0] != name:
                steps.append((name, e.timestamp))
            if e.event_name in conversion:
                break
        steps = steps[-max_length:]
        walks[tuple(n for n, _ in steps)].append([t for _, t in steps])
    ranked = sorted(
        ((path, times) for path, times in walks.items() if len(times) >= min_sessions),
        key=lambda item: -len(item[1]),
    )[:limit]
    answer = {}
    for path, sessions_times in ranked:
        durations = [(t[-1] - t[0]).total_seconds() for t in sessions_times if len(t) >= 2]
        answer[path] = {
            "sessions": len(sessions_times),
            "conversion_rate": round(len(sessions_times) / total, 4),
            "avg_duration_minutes": round(sum(durations) / len(durations) / 60.0, 2)
            if durations
            else 0,
            "step_timings": [
                {
                    "from": path[i],
                    "to": path[i + 1],
                    "avg_minutes": round(
                        sum((t[i + 1] - t[i]).total_seconds() for t in sessions_times)
                        / len(sessions_times)
                        / 60.0,
                        2,
                    ),
                }
                for i in range(len(path) - 1)
            ],
        }
    converting = sum(len(t) for t in walks.values())
    return answer, {
        "total_converting_sessions": converting,
        "paths_analyzed": converting,
        "unique_paths_found": len(walks),
    }


def reference_drop_offs(events, conversion, grouping):
    """Each last event of a session that did not convert: sessions, and the average seconds from
    its first event, sessions of one moment left out, as DropOffView counted them."""
    dropped = defaultdict(list)
    for session in sessions_of(events).values():
        if any(e.event_name in conversion for e in session):
            continue
        seconds = (session[-1].timestamp - session[0].timestamp).total_seconds()
        dropped[grouping.label(session[-1].event_name)].append(seconds or None)
    answer = {}
    for name, times in dropped.items():
        kept = [t for t in times if t is not None]
        answer[name] = {
            "sessions_dropped": len(times),
            "avg_time_before_exit_minutes": round(sum(kept) / len(kept) / 60.0, 2) if kept else 0,
        }
    return answer


def reference_correlation(events, conversion, grouping, min_sessions):
    """Per event (read through the groups, a conversion's group left out): the sessions with it
    and the converting ones among them, held to min_sessions both ways, as EventCorrelationView
    counted them."""
    sessions = sessions_of(events)
    converted = {
        sid for sid, evs in sessions.items() if any(e.event_name in conversion for e in evs)
    }
    left_out = {grouping.label(c) for c in conversion}
    with_event = defaultdict(set)
    for sid, evs in sessions.items():
        for e in evs:
            if grouping.label(e.event_name) not in left_out:
                with_event[grouping.label(e.event_name)].add(sid)
    total = len(sessions)
    answer = {
        name: {"sessions_with_event": len(sids), "converts_with": len(sids & converted)}
        for name, sids in with_event.items()
        if len(sids) >= min_sessions and total - len(sids) >= min_sessions
    }
    return answer, {
        "total_sessions": total,
        "converting_sessions": len(converted),
        "total_event_types": len(with_event),
    }


class BoundedReadsMatchTheirReferenceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = User.objects.create_user(username="owner", password="pw")
        cls.app = App.objects.create(name="Driftnook", user=user)
        other = App.objects.create(name="Lullgate", user=user)
        rng = random.Random(20261026)
        start = timezone.now() - timedelta(days=2)
        events = []
        for s in range(400):
            session = "" if s % 41 == 0 else f"s{s:04d}"
            app = other if s % 23 == 0 else cls.app
            moment = start + timedelta(minutes=rng.randrange(0, 2000))
            for _ in range(rng.randrange(1, 10)):
                moment += timedelta(
                    seconds=rng.randrange(1, 300), microseconds=rng.randrange(10**6)
                )
                events.append(
                    Event(
                        app=app, event_name=rng.choice(NAMES), timestamp=moment, session_id=session
                    )
                )
        Event.objects.bulk_create(events)
        cls.events = [e for e in events if e.app_id == cls.app.id]

    def paths(self, grouping=event_groups.NONE, max_length=10, min_sessions=1, limit=500):
        got = ConversionPathsView()._discover_conversion_paths(
            self.app,
            Event.objects.filter(app=self.app),
            GOAL,
            limit,
            min_sessions,
            max_length,
            grouping,
            slices=slices_in(self.app),
        )
        want, quality = reference_paths(
            self.events, GOAL, max_length, min_sessions, limit, grouping
        )
        by_path = {
            tuple(p["path"]): {k: p[k] for k in want[tuple(p["path"])]} for p in got["paths"]
        }
        self.assertEqual(by_path, want)
        for key, value in quality.items():
            self.assertEqual(got["data_quality"][key], value)
        counts = [p["sessions"] for p in got["paths"]]
        self.assertEqual(counts, sorted(counts, reverse=True))
        return got

    def test_every_path(self):
        got = self.paths()
        self.assertGreater(len(got["paths"]), 5)

    def test_short_paths_a_floor_and_a_limit(self):
        self.paths(max_length=3, min_sessions=2)
        got = self.paths(max_length=2, limit=3)
        self.assertEqual(len(got["paths"]), 3)

    def test_paths_through_a_group(self):
        self.paths(grouping=event_groups.Grouping({"plan": ["plan_a", "plan_b"]}))

    def test_no_conversion_in_range(self):
        got = ConversionPathsView()._discover_conversion_paths(
            self.app, Event.objects.filter(app=self.app), ["never_sent"], slices=slices_in(self.app)
        )
        self.assertEqual(got["paths"], [])
        self.assertEqual(got["data_quality"]["total_converting_sessions"], 0)

    def drop_offs(self, grouping=event_groups.NONE):
        got = DropOffView()._analyze_drop_offs(
            self.app, slices_in(self.app), GOAL, 1, 100, grouping
        )
        want = reference_drop_offs(self.events, GOAL, grouping)
        by_event = {
            p["event"]: {k: p[k] for k in ("sessions_dropped", "avg_time_before_exit_minutes")}
            for p in got["drop_off_points"]
        }
        self.assertEqual(by_event, want)

    def test_drop_offs(self):
        self.drop_offs()

    def test_drop_offs_through_a_group(self):
        self.drop_offs(event_groups.Grouping({"plan": ["plan_a", "plan_b"]}))

    def correlation(self, grouping=event_groups.NONE, min_sessions=1):
        got = EventCorrelationView()._analyze_event_correlations(
            self.app, slices_in(self.app), GOAL, min_sessions, 100, grouping
        )
        want, quality = reference_correlation(self.events, GOAL, grouping, min_sessions)
        rows = got["positive_correlations"] + got["negative_correlations"]
        counted = {
            r["event"]: {
                "sessions_with_event": r["sessions_with_event"],
                "converts_with": r["converts_with"],
            }
            for r in rows
        }
        self.assertEqual(set(counted) | set(got["neutral_events"]), set(want))
        for name, value in counted.items():
            self.assertEqual(value, want[name])
        for key, value in quality.items():
            self.assertEqual(got["data_quality"][key], value)

    def test_correlation(self):
        self.correlation()
        self.correlation(min_sessions=40)

    def test_correlation_through_a_group(self):
        self.correlation(
            event_groups.Grouping({"plan": ["plan_a", "plan_b"], "buying": ["buy", "share"]})
        )

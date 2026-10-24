"""Event groups: events of one kind, counted together and split (BACKLOG, After the move, 1).

`purchase_light` and `purchase_pro` are two events of one kind, and the owner of the app wants
to see `purchase` first and how it splits second. So groups make themselves, and nothing is
asked, but only where the names say plainly that they are kinds of one thing: names that share
their first word (the text before the first `_`, `.`, `-`, `:`, `/` or space) and differ in one
more word that is not a step. `purchase_light` and `purchase_pro`, `subscription_monthly` and
`subscription_annual`, `share_twitter` and `share_facebook` are groups, and the bare `purchase`
joins its own. `purchase_completed` and `purchase_failed`, `onboarding_started` and
`onboarding_completed`, `sign_up` and `sign_in` are not: they are steps or outcomes, and their
sum means nothing (a word in STEPS, or ending in -ed or -ing, is a step). Nor is
`onboarding_step_1`, whose rest is more than one word.

The owner can overrule it from the dashboard, and the choice is kept on the app
(App.event_groups): a group's events can be shown separately, and any events can be put together
under a name of the owner's. An event belongs to one group at most, and a group the owner made
comes first. One place decides, here, for the dashboard and the API alike (the summary's
`event_groups`, and `group_events=true` on the conversion views).

Groups are worked out from every event name the app has sent (`known_names`), never from the
date range on screen, so a group is the same in every tab and every range: `purchase` stays
`purchase` on a day only `purchase_pro` happened.
"""

import hashlib
import re

from django.core.cache import cache
from django.db import connection

SEPARATOR = re.compile(r"[_.\-:/ ]")
MAX_NAME = 255  # as long as an event name may be
MAX_OWN_GROUPS = 50
MAX_GROUP_EVENTS = 50
MAX_NAMES = 2000  # the names an app's groups are worked out from, alphabetically
NAMES_TTL = 600  # seconds an app's list of names is kept in the cache
# Words that name a step or an outcome, never a kind: a group of them would add up stages.
STEPS = frozenset(
    "start begin end open close view show hide click tap press complete finish fail success "
    "error cancel submit attempt request load save delete add remove select enable disable "
    "grant deny allow block skip retry resume pause stop play send receive up in out on off".split()
)


def first_word(name):
    return SEPARATOR.split(name, maxsplit=1)[0]


def is_kind(rest):
    """True for what may follow the shared first word in a group: nothing, or one word that is
    not a step."""
    if not rest:
        return True
    word = rest.lower()
    return not (
        SEPARATOR.search(rest) or word in STEPS or word.endswith(("ed", "ing")) or len(word) > 40
    )


def setting(app):
    """The app's choices, always in the same shape whatever is stored."""
    stored = app.event_groups if isinstance(app.event_groups, dict) else {}
    separate = [g for g in stored.get("separate", []) if isinstance(g, str)]
    own = {
        name: [e for e in events if isinstance(e, str)]
        for name, events in (stored.get("own") or {}).items()
        if isinstance(name, str) and isinstance(events, list)
    }
    return {"separate": separate, "own": own}


def groups(names, choices):
    """{group: [its event names]} among `names`, owner's groups first, then automatic ones."""
    names = set(names)
    found = {}
    taken = set()
    for name, events in choices["own"].items():
        present = [e for e in events if e in names and e not in taken]
        if present:
            found[name] = present
            taken.update(present)
    words = {}
    for event in sorted(names - taken):
        word = first_word(event)
        if word:
            words.setdefault(word, []).append(event)
    for word, events in words.items():
        if len(events) < 2 or word in choices["separate"] or word in found:
            continue
        if all(is_kind(event[len(word) + 1 :]) for event in events):
            found[word] = events
    return found


def known_names(app_id):
    """Every event name the app has sent, alphabetically. Read from the (app, event_name,
    timestamp) index one name at a time, each probe starting after the last name found, so it
    costs one short index read per name, never a read of the app's events; kept for NAMES_TTL."""
    key = f"event_names:{app_id}"
    names = cache.get(key)
    if names is None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                WITH RECURSIVE names(name, n) AS (
                    (SELECT event_name, 1 FROM "analytics_event"
                     WHERE app_id = %s ORDER BY event_name LIMIT 1)
                    UNION ALL
                    SELECT (SELECT e.event_name FROM "analytics_event" e
                            WHERE e.app_id = %s AND e.event_name > names.name
                            ORDER BY e.event_name LIMIT 1), n + 1
                    FROM names WHERE names.name IS NOT NULL AND n < %s
                )
                SELECT name FROM names WHERE name IS NOT NULL
                """,
                [app_id, app_id, MAX_NAMES],
            )
            names = [row[0] for row in cursor.fetchall()]
        cache.set(key, names, NAMES_TTL)
    return names


def app_groups(app):
    """{group: [its events]} for the app, owner's groups first, from every name it has sent."""
    return groups(known_names(app.id), setting(app))


def state(app):
    """What the dashboard shows and changes: every group with its events and whether the
    product made it, the first words shown separately, and every event name, to group."""
    choices = setting(app)
    return {
        "groups": [
            {"name": name, "automatic": name not in choices["own"], "events": sorted(events)}
            for name, events in app_groups(app).items()
        ],
        "separate": choices["separate"],
        "events": known_names(app.id),
    }


class Grouping:
    """One app's groups applied to event names: each grouped event reads as its group's name,
    as the conversion views do with `group_events=true`. `Grouping()` changes nothing."""

    def __init__(self, found=None):
        self.groups = found or {}
        self.group_of = {e: g for g, events in self.groups.items() for e in events}

    @classmethod
    def of(cls, app):
        return cls(app_groups(app))

    def label(self, name):
        return self.group_of.get(name, name)

    def expand(self, names):
        """Names where a group's name stands for its events, as a funnel step chosen as a group
        does; any other name stands for itself."""
        return list(dict.fromkeys(e for name in names for e in self.groups.get(name, [name])))

    def key(self):
        """What a cached answer read through these groups adds to its key, so a change to the
        groups is never hidden behind an answer read through the old ones."""
        if not self.group_of:
            return "none"
        return hashlib.md5(repr(sorted(self.group_of.items())).encode()).hexdigest()[:12]

    def sql(self, column):
        """`column` read through the groups, as SQL with its parameters, so a session that holds
        purchase_light and purchase_pro holds purchase once when it is counted."""
        if not self.group_of:
            return column, []
        pairs = sorted(self.group_of.items())
        cases = " ".join(["WHEN %s THEN %s"] * len(pairs))
        return f"(CASE {column} {cases} ELSE {column} END)", [x for pair in pairs for x in pair]


NONE = Grouping()  # every event read by its own name


def from_request(request, app):
    """The app's groups where a request asks for them (`group_events=true`), else none: an API
    caller who never asked keeps reading every event by its own name."""
    asked = (request.query_params.get("group_events") or "").strip().lower()
    return Grouping.of(app) if asked in ("1", "true", "yes") else NONE


def summarize(counts, app):
    """The groups among an app's event counts ({event_name: count}), largest first:
    [{"name", "total", "automatic", "events": [{"event_name", "count"}, ...]}]. A group is
    listed when any of its events is in `counts`."""
    choices = setting(app)
    summary = []
    for name, events in app_groups(app).items():
        members = sorted(
            ({"event_name": e, "count": counts[e]} for e in events if e in counts),
            key=lambda m: (-m["count"], m["event_name"]),
        )
        if not members:
            continue
        summary.append(
            {
                "name": name,
                "total": sum(m["count"] for m in members),
                "automatic": name not in choices["own"],
                "events": members,
            }
        )
    return sorted(summary, key=lambda g: (-g["total"], g["name"]))


class Refused(ValueError):
    """A change the dashboard cannot make, with the words to show for it."""


def change(app, action, name, events, known_events):
    """Apply one change from the dashboard to App.event_groups and save it.

    `known_events` are the app's own event names: a group may only hold events the app sends.
    """
    choices = setting(app)
    name = (name or "").strip()
    if not name or len(name) > MAX_NAME:
        raise Refused("Give the group a name of up to 255 characters.")
    if action == "separate":
        if name not in choices["separate"]:
            choices["separate"].append(name)
    elif action == "group_again":
        choices["separate"] = [g for g in choices["separate"] if g != name]
    elif action == "remove":
        choices["own"].pop(name, None)
    elif action == "create":
        chosen = sorted({e for e in events or [] if isinstance(e, str)} & set(known_events))
        if len(chosen) < 2:
            raise Refused("Choose at least two events for the group.")
        if name in known_events and name not in chosen:
            raise Refused("An event already has that name. Choose another, or add that event.")
        if len(chosen) > MAX_GROUP_EVENTS:
            raise Refused(f"A group can hold up to {MAX_GROUP_EVENTS} events.")
        if name not in choices["own"] and len(choices["own"]) >= MAX_OWN_GROUPS:
            raise Refused(f"An app can have up to {MAX_OWN_GROUPS} groups of its own.")
        # an event belongs to one group: it leaves any other group of the owner's
        for other, members in list(choices["own"].items()):
            if other != name:
                left = [e for e in members if e not in chosen]
                if len(left) >= 2:
                    choices["own"][other] = left
                else:
                    del choices["own"][other]
        choices["own"][name] = chosen
    else:
        raise Refused("That change is not one the dashboard makes.")
    app.event_groups = choices
    app.save(update_fields=["event_groups"])
    return choices


def with_groups(summary, app):
    """The events summary with its `event_groups`, worked out after the cache, so a change the
    owner makes shows at once and never waits for a cached summary to expire."""
    return {**summary, "event_groups": summarize(summary.get("events_by_name") or {}, app)}

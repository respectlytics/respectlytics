"""What the public API reference shows, in both editions, and the words it uses.

Two keys reach the API. The app key ships inside every copy of an app, so it can send events
and nothing else. The account's secret key (analytics.models.SecretKey), sent with the app key
naming the app, reads and deletes that app's data. Until 2026-10-22 this reference listed
every endpoint under the app key, where they answer 401, with response examples carrying
fields the API never returned. The published operations are documented here, in one place,
and core/test_api_schema.py calls each one and holds its example to the real answer.
"""

from drf_yasg import openapi
from drf_yasg.generators import OpenAPISchemaGenerator

APP_KEY = "App key"
SECRET_KEY = "Secret key"

SECURITY_DEFINITIONS = {
    APP_KEY: {
        "type": "apiKey",
        "name": "X-App-Key",
        "in": "header",
        "description": (
            "The app key from your dashboard, in the X-App-Key header. It ships inside your "
            "app, so it can send events and nothing else."
        ),
    },
    SECRET_KEY: {
        "type": "apiKey",
        "name": "Authorization",
        "in": "header",
        "description": (
            "A secret key from Account Settings, Secret Keys, sent as "
            "`Authorization: Bearer rl_secret_...` together with the app key of the app. "
            "Keep it on your own server or computer, never in an app."
        ),
    },
}

# The reference's own words about the two keys and what they open, in both editions
# (.format(site=...) with the edition's address).
KEYS_AND_ENDPOINTS = """## Authentication

**Sending events** takes the app key in the `X-App-Key` header:

```
X-App-Key: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

The app key ships inside your app, so it can send events and nothing else.

**Reading and deleting** takes a secret key, made in
[Account Settings, Secret Keys](/account/api-keys/), together with the app key of the app you want:

```
curl {site}/api/v1/events/summary/ \\
  -H "Authorization: Bearer rl_secret_..." \\
  -H "X-App-Key: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

A secret key reads and deletes the data of every app in your account, so keep it on your own
server or computer and never put it in an app. Revoke it on the same page if it leaks.

## Endpoints

- **POST /api/v1/events/**: send one event (app key)
- **GET /api/v1/events/summary/**, **count/**, **event-types/**, **geo-summary/**, **funnel/**,
  **export/**: read and export (secret key)
- **POST /api/v1/events/delete/preview/**, **POST /api/v1/events/delete/**,
  **GET /api/v1/events/deletions/**: delete events and read the history (secret key)
"""


WHICH_APP = openapi.Parameter(
    "X-App-Key",
    openapi.IN_HEADER,
    description="The app key of the app to read. The secret key proves the app is yours.",
    type=openapi.TYPE_STRING,
    required=True,
)


def _query(name, description, type_=openapi.TYPE_STRING, required=False):
    return openapi.Parameter(
        name, openapi.IN_QUERY, description=description, type=type_, required=required
    )


FROM = _query("from", "First day, YYYY-MM-DD. Without it, from the first event.")
TO = _query("to", "Last day, YYYY-MM-DD. Without it, up to now.")
TZ = _query("tz", "The time zone the days are counted in, such as Europe/Berlin. Default UTC.")
PLATFORM = "Only this platform: ios, android, web or other"
COUNTRY = "Only this country, in two letters, such as SE"

FILTER_BODY = openapi.Parameter(
    "filters",
    openapi.IN_BODY,
    required=True,
    schema=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["date_from", "date_to"],
        properties={
            "date_from": openapi.Schema(type=openapi.TYPE_STRING, description="First day"),
            "date_to": openapi.Schema(type=openapi.TYPE_STRING, description="Last day"),
            "platform": openapi.Schema(type=openapi.TYPE_STRING, description=PLATFORM),
            "country": openapi.Schema(type=openapi.TYPE_STRING, description=COUNTRY),
            "event_name": openapi.Schema(type=openapi.TYPE_STRING, description="Only this event"),
        },
    ),
)

# Each operation the secret key opens: (summary, description, parameters, example of a 200
# answer). Every field in an example is one the API returns.
SECRET_KEY_OPERATIONS = {
    ("/api/v1/events/summary/", "GET"): (
        "Summary",
        "Events by name, by day and by country for a range of days. `unique_buckets` is "
        "the number of sessions that day. `event_groups` counts events of one kind together: "
        "events whose names start with the same word (`purchase_light` and `purchase_pro` are "
        "`purchase`), and the groups the app's owner made in the dashboard. A group is worked "
        "out from every event the app has sent, so it is the same in every range.",
        [WHICH_APP, FROM, TO, TZ],
        {
            "app_name": "Recipe Box",
            "total_events": 1520,
            "events_by_name": {
                "app_open": 900,
                "recipe_saved": 520,
                "purchase_pro": 60,
                "purchase_light": 40,
            },
            "events_by_day": [{"date": "2026-10-20", "count": 1520, "unique_buckets": 310}],
            "top_countries": [{"country": "SE", "count": 800}, {"country": "DE", "count": 420}],
            "unique_countries": 12,
            "event_groups": [
                {
                    "name": "purchase",
                    "total": 100,
                    "automatic": True,
                    "events": [
                        {"event_name": "purchase_pro", "count": 60},
                        {"event_name": "purchase_light", "count": 40},
                    ],
                }
            ],
        },
    ),
    ("/api/v1/events/count/", "GET"): (
        "Count",
        "How many events arrived in a range of days.",
        [WHICH_APP, FROM, TO, TZ],
        {"total_events": 1520, "date_range": {"from": "2026-10-01", "to": "2026-10-31"}},
    ),
    ("/api/v1/events/event-types/", "GET"): (
        "Event names",
        "Every event name the app has sent.",
        [WHICH_APP],
        {
            "app_name": "Recipe Box",
            "event_types": ["app_open", "purchase_pro", "recipe_saved"],
            "count": 3,
        },
    ),
    ("/api/v1/events/geo-summary/", "GET"): (
        "Countries",
        "Events per country for a range of days.",
        [WHICH_APP, FROM, TO, TZ, _query("limit", "At most this many countries. Default 20.")],
        {
            "app_name": "Recipe Box",
            "total_events": 1520,
            "countries": [
                {"country": "SE", "count": 800, "percentage": 52.6},
                {"country": "DE", "count": 420, "percentage": 27.6},
            ],
        },
    ),
    ("/api/v1/events/funnel/", "GET"): (
        "Funnel",
        "How many sessions reached each step, in order.",
        [
            WHICH_APP,
            _query("steps", "Event names in order, separated by commas.", required=True),
            _query(
                "group_events",
                "true lets a step be an event group's name (see `event_groups` in the summary), "
                "standing for any of its events. Default false.",
                openapi.TYPE_BOOLEAN,
            ),
            FROM,
            TO,
            TZ,
            _query("platform", f"{PLATFORM}."),
            _query("country", f"{COUNTRY}."),
            _query(
                "window_minutes",
                "Longest time allowed between two steps, in minutes. Default no limit.",
                openapi.TYPE_INTEGER,
            ),
        ],
        {
            "app_name": "Recipe Box",
            "funnel": [{"step": "app_open", "count": 1000}, {"step": "purchase_pro", "count": 90}],
            "total_sessions_analyzed": 1200,
        },
    ),
    ("/api/v1/events/export/", "GET"): (
        "Export",
        "Every event in a range of days, as CSV (the default) or JSON, at most 90 days and "
        "100,000 events at a time. Without days, the last 90.",
        [
            WHICH_APP,
            _query("output", "csv or json. Default csv."),
            FROM,
            TO,
            _query("event_name", "Only this event."),
            _query("platform", f"{PLATFORM}."),
            _query("country", f"{COUNTRY}."),
        ],
        {
            "metadata": {
                "app_name": "Recipe Box",
                "app_slug": "recipe-box",
                "export_date": "2026-10-23T09:00:00",
                "date_range": {"from": "2026-10-01", "to": "2026-10-31"},
                "total_events": 1520,
                "filters_applied": {"from_date": "2026-10-01", "to_date": "2026-10-31"},
                "export_format": "json",
                "limits": {"max_days": 90, "max_events": 100000},
            },
            "events": [
                {
                    "id": "0b6f4d2e-8c1a-4f3b-9e7d-2a5c6b8d9e01",
                    "event_name": "purchase_pro",
                    "timestamp": "2026-10-20T10:02:00+00:00",
                    "session_id": "9f1c3e5a7b2d4f6081a3c5e7f9b1d3a5",
                    "country": "SE",
                    "platform": "ios",
                }
            ],
        },
    ),
    ("/api/v1/events/delete/preview/", "POST"): (
        "Preview a deletion",
        "How many events a deletion with these filters would remove. Nothing is deleted. "
        "Days are YYYY-MM-DD.",
        [WHICH_APP, FILTER_BODY],
        {"events_matching": 1523},
    ),
    ("/api/v1/events/delete/", "POST"): (
        "Delete events",
        "Deletes every event that matches the filters, for good, and records the deletion "
        "in the history. Days are YYYY-MM-DD.",
        [WHICH_APP, FILTER_BODY],
        {"events_deleted": 1523, "deletion_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"},
    ),
    ("/api/v1/events/deletions/", "GET"): (
        "Deletion history",
        "Every deletion made in the app, newest first.",
        [WHICH_APP],
        {
            "deletions": [
                {
                    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "deleted_at": "2026-10-20T14:30:00Z",
                    "events_deleted": 1523,
                    "filter_date_from": "2026-01-01",
                    "filter_date_to": "2026-01-31",
                    "filter_platform": None,
                    "filter_country": "SE",
                    "filter_event_name": None,
                }
            ]
        },
    ),
}
APP_KEY_OPERATIONS = {("/api/v1/events/", "POST")}


class PublicEndpoints(OpenAPISchemaGenerator):
    """The public reference: sending events with the app key, and the reads and deletions the
    secret key opens, each documented from SECRET_KEY_OPERATIONS."""

    def get_security_definitions(self):
        return SECURITY_DEFINITIONS

    def get_security_requirements(self, security_definitions):
        return []  # each operation names the key it takes

    def get_endpoints(self, request):
        published = APP_KEY_OPERATIONS | set(SECRET_KEY_OPERATIONS)
        public = {}
        for path, (view_cls, methods) in super().get_endpoints(request).items():
            kept = [(method, view) for method, view in methods if (path, method) in published]
            if kept:
                public[path] = (view_cls, kept)
        return public

    def get_operation(self, view, path, prefix, method, components, request):
        operation = super().get_operation(view, path, prefix, method, components, request)
        if (path, method) in APP_KEY_OPERATIONS:
            operation.security = [{APP_KEY: []}]
            return operation
        summary, description, parameters, example = SECRET_KEY_OPERATIONS[(path, method)]
        operation.summary = summary
        operation.description = description
        operation.security = [{SECRET_KEY: []}]
        operation.parameters = parameters
        operation.responses = openapi.Responses(
            {
                "200": openapi.Response("OK", examples={"application/json": example}),
                "400": openapi.Response("A parameter is missing or not valid"),
                "401": openapi.Response("The secret key or the app key is not valid"),
            }
        )
        return operation

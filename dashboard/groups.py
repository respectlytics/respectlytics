"""The dashboard's read and write of the event groups (analytics/event_groups.py).

Its own module, not dashboard/views.py, because the community edition replaces that file with
its own (_oss_overrides/dashboard/views.py) and both editions route here.
"""

import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from analytics import access, event_groups
from analytics.models import App, Event


@require_http_methods(["GET", "POST"])
def update_event_groups(request, app_slug):
    """
    Read or change the app's event groups, from the stats page's Event groups panel.

    GET answers the groups as every tab shows them (event_groups.state):
        {"groups": [{"name", "automatic", "events"}], "separate": [...], "events": [...]}

    POST changes them, with a JSON body:
        {"action": "separate" | "group_again" | "create" | "remove",
         "name": "purchase", "events": ["purchase_light", "purchase_pro"]}
    `events` is read for "create" only, and keeps only events the app has sent. It answers
    {"success": true, **state}.
    """
    # Reading: the owner, a member or a share link; changing: the owner or an editor
    level = access.VIEW if request.method == "GET" else access.EDIT
    if not request.user.is_authenticated and not request.headers.get("X-Share-Token"):
        return JsonResponse({"error": "Sign in"}, status=401)
    try:
        app = access.app_for_request(request, level, slug=app_slug)
    except App.DoesNotExist:
        return JsonResponse({"error": "App not found"}, status=404)
    if request.method == "GET":
        return JsonResponse(event_groups.state(app))
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    action = data.get("action")
    asked = [e for e in data.get("events") or [] if isinstance(e, str)]
    # One indexed EXISTS per chosen event (app, event_name, timestamp), each stopping at its
    # first row: a DISTINCT over the app's events would read every purchase it ever sent.
    # The group's own name is asked too: it may not be an event outside the group.
    known = set()
    if action == "create":
        name = data.get("name")
        candidates = asked[: event_groups.MAX_GROUP_EVENTS + 1]
        if isinstance(name, str):
            candidates = [*candidates, name.strip()]
        for candidate in dict.fromkeys(candidates):
            if Event.objects.filter(app=app, event_name=candidate).exists():
                known.add(candidate)
    try:
        event_groups.change(app, action, data.get("name"), asked, known)
    except event_groups.Refused as refused:
        return JsonResponse({"error": str(refused)}, status=400)
    return JsonResponse({"success": True, **event_groups.state(app)})

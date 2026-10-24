"""{% app_nav "stats" %}: an app's sidebar (dashboard/partials/_app_nav.html), with its tabs and
where they lead, for the app's own pages, a share link's and the public demo's."""

from django import template
from django.urls import NoReverseMatch, reverse

from analytics import access

register = template.Library()

TABS = [
    ("overview", "Overview"),
    ("conversion", "Conversion"),
    ("behavior", "Behavior"),
    ("segments", "Segments"),
]


def _exists(name, *args):
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        return None


@register.inclusion_tag("dashboard/partials/_app_nav.html", takes_context=True)
def app_nav(context, here):
    slug = context.get("app_slug")
    token = context.get("share_token")
    tabs = list(TABS)
    # A/B tests where respectlytics.com has them (properties/)
    if _exists("properties:experiments", slug):
        tabs.append(("experiments", "A/B tests"))
    demo = bool(context.get("demo"))
    if demo:
        stats_url = reverse("demo:dashboard")
        funnel_url = reverse("demo:funnel")
    elif token:
        stats_url = reverse("teams:shared", args=[token])
        funnel_url = reverse("teams:shared_funnel", args=[token])
    else:
        stats_url = reverse("dashboard:stats", args=[slug])
        funnel_url = reverse("dashboard:funnel", args=[slug])
    return {
        "here": here,
        "tabs": tabs,
        "stats_url": stats_url,
        "funnel_url": funnel_url,
        "app_slug": slug,
        "share_token": token,
        # Seen from outside the account (a share link, the demo): no app list, no settings
        "outside": bool(token) or demo,
        "app_name": context.get("app_name") or getattr(context.get("app"), "name", ""),
        "not_owner": context.get("not_owner"),
    }


@register.inclusion_tag("partials/app_switcher.html", takes_context=True)
def app_switcher(context):
    """The top bar's app switcher (partials/app_bar.html): shown on an app's own pages, for the
    person signed in, with every app they may open, their own and those shared with them."""
    request = context.get("request")
    slug = context.get("app_slug")
    user = getattr(request, "user", None)
    if not slug or user is None or not user.is_authenticated:
        return {"show": False}
    if context.get("demo") or context.get("share_token"):
        return {"show": False}
    apps = list(access.apps_for(user).order_by("name").values("name", "slug", "user_id"))
    current = next((a for a in apps if a["slug"] == slug), None)
    return {"show": current is not None, "current": current, "apps": apps, "own_id": user.pk}

"""Who may do what with an app: one place, for the dashboard, the API and the jobs.

An app belongs to the account that made it. On a paid plan its owner can bring team members
(teams/, respectlytics.com only): a viewer reads every app of the account, an editor also
changes how they read (event groups, conversion events, properties, A/B tests, alerts, share
links). Billing, the team, secret keys and deleting data stay the owner's. A member's access
lasts while the owner's plan includes the team (billing/features.py), and ends the moment the
owner removes them or the plan ends, because it is worked out on every request.

Where teams/ is not installed (the community edition), every app is its owner's alone.
"""

from django.apps import apps as installed
from django.db.models import Q

from .models import App

VIEW, EDIT, OWN = 1, 2, 3


def _teams():
    return installed.is_installed("teams")


def owners_for(user, level=VIEW):
    """The accounts whose apps `user` may open at `level`, their own first."""
    if user is None or not user.is_authenticated:
        return []
    owners = [user.pk]
    if _teams() and level < OWN:
        from teams.models import Membership

        owners += Membership.owners_for(user, editor=level >= EDIT)
    return owners


def apps_for(user, level=VIEW):
    """Every app `user` may open at `level`."""
    return App.objects.filter(user_id__in=owners_for(user, level))


def app_for(user, level=VIEW, **lookup):
    """The app `lookup` names (slug=..., id=...) if `user` may open it at `level`; raises
    App.DoesNotExist otherwise, so a stranger learns nothing, not even that it exists."""
    return apps_for(user, level).get(**lookup)


def role(user, app):
    """OWN, EDIT, VIEW or 0: what `user` may do with `app`."""
    if user is None or not user.is_authenticated:
        return 0
    if app.user_id == user.pk:
        return OWN
    for level in (EDIT, VIEW):
        if app.user_id in owners_for(user, level):
            return level
    return 0


def own_or_member_q(user):
    """The same rule as a filter on App, for a query that joins it."""
    return Q(user_id__in=owners_for(user))


def app_for_request(request, level=VIEW, **lookup):
    """The app a dashboard endpoint names, for the person signed in or, to read only, for a
    share link's token in the X-Share-Token header (teams/); raises App.DoesNotExist when
    neither may open it at `level`."""
    token = request.headers.get("X-Share-Token")
    if token:
        if level > VIEW or request.method not in ("GET", "HEAD") or not _teams():
            raise App.DoesNotExist
        from teams.models import ShareLink

        link = ShareLink.find(token)
        if link is None:
            raise App.DoesNotExist
        link.note_use()
        return App.objects.filter(pk=link.app_id).get(**lookup)
    return app_for(request.user, level, **lookup)

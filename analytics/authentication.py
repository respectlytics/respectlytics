from django.core.exceptions import ValidationError
from rest_framework.authentication import BaseAuthentication, SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed

from . import access
from .models import App, SecretKey


def _note_role(request, role):
    """What the authenticated person may do with the app, for a view that needs more than
    reading (deleting events is the owner's): request.user is the App, so it travels here."""
    request._request.app_role = role


def app_key_from(request):
    """The app key a request names: the X-App-Key header, the app_key query parameter,
    or app_key in the body of a POST, PUT or PATCH."""
    app_key = request.headers.get("X-App-Key") or request.query_params.get("app_key")
    if not app_key and request.method in ("POST", "PUT", "PATCH"):
        app_key = request.data.get("app_key")
    return app_key


class AppKeyAuthentication(BaseAuthentication):
    """
    Custom authentication class for app_key based authentication.

    Clients must provide an app_key in one of these ways:
    1. HTTP Header: X-App-Key: <uuid>
    2. Query Parameter: ?app_key=<uuid>
    3. Request Body: {"app_key": "<uuid>", ...}
    """

    def authenticate(self, request):
        app_key = app_key_from(request)

        # If no app_key provided, return None (anonymous user)
        if not app_key:
            return None

        # Try to find the app
        try:
            app = App.objects.get(id=app_key)
            # Return (user, auth) tuple - we use app as the "user"
            return (app, app_key)
        except (App.DoesNotExist, ValueError, ValidationError):
            # ValueError: invalid UUID format
            # ValidationError: from Django UUID field
            raise AuthenticationFailed("Invalid app_key") from None

    def authenticate_header(self, request):
        """
        Return the WWW-Authenticate header value for 401 responses.
        """
        return "X-App-Key"


class AppOwnerSessionAuthentication(SessionAuthentication):
    """Everything that reads, exports or deletes an app's data: the signed-in owner only.

    The app key ships inside every copy of a customer's app, so anyone can pull it out of a
    published app. It may only send events (EventCreateView keeps AppKeyAuthentication).
    Reading, exporting and deleting are for the person signed in to the dashboard who owns
    the app; the key in the request only says which of their apps. Without a session, or for
    an app that is not theirs, the request is refused (401). Without an app key it
    authenticates nothing, so a view that needs no app (the staff schema) falls through to
    the plain session. Unsafe methods are checked for CSRF,
    as every session request is. request.user is the App, as with AppKeyAuthentication, so
    the views read it the same way.
    """

    def authenticate(self, request):
        signed_in = super().authenticate(request)
        if signed_in is None:
            return None
        app_key = app_key_from(request)
        if not app_key:
            return None
        # The owner, or a member of the owner's team (analytics/access.py)
        try:
            app = access.app_for(signed_in[0], id=app_key)
        except (App.DoesNotExist, ValueError, ValidationError):
            raise AuthenticationFailed("Invalid app_key") from None
        _note_role(request, access.role(signed_in[0], app))
        return (app, app_key)

    def authenticate_header(self, request):
        """A 401, not a 403, for a request that is not signed in or names an app not theirs."""
        return "Session"


class SecretKeyAuthentication(BaseAuthentication):
    """Reading, exporting and deleting through the API without a browser: the account's
    secret key (analytics.models.SecretKey) in `Authorization: Bearer`, and the app key naming
    which of the account's apps, as with the session. Read from that header only, never from
    a URL, which ends up in browser histories and logs.

    A request without the header falls through to the session (AppOwnerSessionAuthentication);
    one with a key that does not work, or naming an app of another account, is refused (401),
    which counts toward blocking the address (analytics/middleware.py).
    """

    keyword = "bearer"

    def authenticate(self, request):
        kind, _, key = request.headers.get("Authorization", "").partition(" ")
        if kind.lower() != self.keyword:
            return None
        row = SecretKey.find(key.strip())
        if row is None or not row.user.is_active:
            raise AuthenticationFailed("Invalid secret key")
        app_key = app_key_from(request)
        if not app_key:
            raise AuthenticationFailed("Name the app with its app key in the X-App-Key header")
        try:
            app = App.objects.get(id=app_key, user=row.user)
        except (App.DoesNotExist, ValueError, ValidationError):
            raise AuthenticationFailed("Invalid app_key") from None
        row.note_use()
        _note_role(request, access.OWN)
        return (app, app_key)

    def authenticate_header(self, request):
        return 'Bearer realm="api"'


class ShareLinkAuthentication(BaseAuthentication):
    """A share link's dashboard (teams/): the token in the X-Share-Token header reads the one
    app it was made for, on the views that say so (`share_links = True`), and only reads. Any
    other view, method or app is refused, so a link can never export, delete or reach a key.
    Without teams/ (the community edition) it authenticates nothing.
    """

    header = "X-Share-Token"

    def authenticate(self, request):
        token = request.headers.get(self.header)
        if not token:
            return None
        view = (getattr(request, "parser_context", None) or {}).get("view")
        if request.method not in ("GET", "HEAD") or not getattr(view, "share_links", False):
            raise AuthenticationFailed("A share link only reads its dashboard")
        from django.apps import apps

        if not apps.is_installed("teams"):
            raise AuthenticationFailed("Invalid share link")
        from teams.models import ShareLink

        link = ShareLink.find(token)
        if link is None or str(link.app_id) != str(app_key_from(request) or link.app_id):
            raise AuthenticationFailed("Invalid share link")
        link.note_use()
        _note_role(request, access.VIEW)
        return (link.app, str(link.app_id))

    def authenticate_header(self, request):
        return self.header


# Every view that reads, exports or deletes an app's data: the secret key, else the session,
# else (on the views that allow it, and only to read) a share link.
APP_OWNER = [SecretKeyAuthentication, ShareLinkAuthentication, AppOwnerSessionAuthentication]

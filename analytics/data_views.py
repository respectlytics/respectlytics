"""Every view that reads an app's data: those whose authentication is APP_OWNER (the secret key,
a share link or the signed-in owner). The features that report on an app's data decide, for each
of them, what they say about it, and their tests read this one list, the weekly email's
(conversion/test_insights.py) among them."""

from django.urls import URLPattern, URLResolver, get_resolver


def data_views() -> set[str]:
    from .authentication import APP_OWNER

    def walk(patterns):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                yield from walk(pattern.url_patterns)
            elif isinstance(pattern, URLPattern):
                yield getattr(pattern.callback, "view_class", None)

    return {
        view.__name__
        for view in walk(get_resolver().url_patterns)
        if view is not None and list(getattr(view, "authentication_classes", [])) == APP_OWNER
    }

import logging

from django.conf import settings
from django.core.cache import cache
from rest_framework.throttling import SimpleRateThrottle

from .blocks import AUTH, address_key, block, blockable
from .client_ip import get_client_ip

logger = logging.getLogger(__name__)


class AnonRateThrottle(SimpleRateThrottle):
    """
    SEC-001: Throttle for anonymous/unauthenticated API requests.

    Currently reserved for future public endpoints. All current endpoints
    require authentication (session or app_key), so this is not applied.

    Potential future use cases:
    - Public API endpoints (if added)
    - Contact form submissions
    - Public documentation/stats endpoints

    Default: 10 requests per hour per IP

    To apply to a view:
        from rest_framework.decorators import throttle_classes

        @throttle_classes([AnonRateThrottle])
        def public_view(request):
            ...
    """

    scope = "anon"
    rate = getattr(settings, "ANON_THROTTLE_RATE", "10/hour")

    def get_cache_key(self, request, view):
        # Only throttle if no authentication
        if hasattr(request, "user") and request.user:
            return None  # Don't throttle authenticated requests

        ident = get_client_ip(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


def track_failed_auth_attempt(request, app_key=None):
    """
    Count a refused API key from this address; 10 within 15 minutes block it for an hour
    (analytics/blocks.py). The count is filed under the address's code, never the address.
    Returns whether this attempt blocked it.

    Fails open: if the cache/DB is unreachable (e.g. during maintenance),
    logs a warning and returns False rather than crashing the request.
    """
    ip = get_client_ip(request)
    if not blockable(ip):
        return False
    cache_key = f"failed_auth:{address_key(ip)}"

    try:
        attempts = cache.get(cache_key, 0) + 1
        cache.set(cache_key, attempts, 900)  # 15 minutes
        if attempts >= 10:
            cache.delete(cache_key)
            return block(ip, AUTH, f"{attempts} refused API keys within 15 minutes") is not None
    except Exception:
        logger.warning("[SECURITY] Cache unavailable during auth tracking, failing open")

    return False

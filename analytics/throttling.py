from rest_framework.throttling import SimpleRateThrottle
from django.core.cache import cache
from django.conf import settings
import logging

from .client_ip import get_client_ip

logger = logging.getLogger(__name__)

# Addresses that many unrelated clients share, so a ban on one shuts out all of
# them. Cloudflare sends every Worker's request to another site from this one
# address, whoever runs the Worker: a customer sending events from a Worker and
# any scanner someone runs on Workers are the same visitor here. Its bad requests
# are still refused one at a time, but it is never banned from the whole site:
# on 2026-10-13 a WordPress scanner got it banned at loheden.com, and the uptime
# watchdog with it.
# https://developers.cloudflare.com/fundamentals/reference/http-headers/
SHARED_ADDRESSES = frozenset({'2a06:98c0:3600::103'})


def ban_ip(ip, seconds):
    """Refuse every request from this address for a while. Returns whether it did."""
    if ip in SHARED_ADDRESSES:
        return False
    cache.set(f'banned:{ip}', True, seconds)
    return True


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
    scope = 'anon'
    rate = getattr(settings, 'ANON_THROTTLE_RATE', '10/hour')
    
    def get_cache_key(self, request, view):
        # Only throttle if no authentication
        if hasattr(request, 'user') and request.user:
            return None  # Don't throttle authenticated requests
        
        ident = get_client_ip(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }


def track_failed_auth_attempt(request, app_key=None):
    """
    Track failed authentication attempts to detect brute force attacks.
    Blocks after 10 failed attempts in 15 minutes.
    
    Fails open: if the cache/DB is unreachable (e.g. during maintenance),
    logs a warning and returns False rather than crashing the request.
    """
    ip = get_client_ip(request)
    cache_key = f'failed_auth:{ip}'
    
    try:
        attempts = cache.get(cache_key, 0)
        attempts += 1
        cache.set(cache_key, attempts, 900)  # 15 minutes
        
        if attempts >= 10:
            logger.warning(f"[SECURITY] Multiple failed auth attempts from IP: {ip}, app_key: {app_key}")
            return ban_ip(ip, 3600)  # Ban for 1 hour
    except Exception:
        logger.warning(f"[SECURITY] Cache unavailable during auth tracking for IP: {ip} — failing open")
    
    return False


def is_ip_banned(request):
    """
    Check if IP is temporarily banned.
    
    In DEBUG mode, localhost (127.0.0.1) is never banned to allow
    SDK integration testing without getting locked out.
    
    Fails open: if the cache/DB is unreachable (e.g. during maintenance),
    logs a warning and returns False rather than crashing the request.
    """
    ip = get_client_ip(request)
    
    # In development, never ban localhost - allows SDK testing
    if settings.DEBUG and ip in ('127.0.0.1', 'localhost', '::1'):
        return False
    
    try:
        return cache.get(f'banned:{ip}', False)
    except Exception:
        logger.warning(f"[SECURITY] Cache unavailable checking ban for IP: {ip} — failing open")
        return False

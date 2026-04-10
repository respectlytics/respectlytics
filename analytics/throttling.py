from rest_framework.throttling import SimpleRateThrottle
from django.core.cache import cache
from django.conf import settings
import logging

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
    scope = 'anon'
    rate = getattr(settings, 'ANON_THROTTLE_RATE', '10/hour')
    
    def get_cache_key(self, request, view):
        # Only throttle if no authentication
        if hasattr(request, 'user') and request.user:
            return None  # Don't throttle authenticated requests
        
        ident = self.get_ident(request)
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
            cache.set(f'banned:{ip}', True, 3600)  # Ban for 1 hour
            return True
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


def get_client_ip(request):
    """Get client IP address, considering proxies"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

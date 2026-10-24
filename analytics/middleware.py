import logging
import re

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponseForbidden, HttpResponsePermanentRedirect
from django.utils.deprecation import MiddlewareMixin

from .blocks import ATTACK, SCAN, active_block, address_key, block, blockable, refused
from .client_ip import get_client_ip
from .throttling import track_failed_auth_attempt

logger = logging.getLogger(__name__)


# =============================================================================
# SEO: www to non-www redirect middleware
# =============================================================================


class WwwRedirectMiddleware(MiddlewareMixin):
    """
    Redirect www.respectlytics.com to respectlytics.com (301 permanent).

    This prevents duplicate content issues where Google indexes both
    www and non-www versions of URLs. The canonical version is non-www.

    Only active in production (when DEBUG=False).
    """

    def process_request(self, request):
        """Redirect www requests to non-www."""
        if settings.DEBUG:
            return None  # Skip in development

        host = request.get_host().lower()
        if host.startswith("www."):
            # Build the non-www URL with same path and query string
            new_host = host[4:]  # Remove 'www.'
            new_url = f"https://{new_host}{request.get_full_path()}"
            return HttpResponsePermanentRedirect(new_url)

        return None


# =============================================================================
# The door: blocked visitors, attack signals and 404 scans (analytics/blocks.py)
# =============================================================================

# Missing pages that never count toward a scan: a page whose images or files are
# missing makes many 404s of its own, the signed-in dashboard and the API have their
# own checks, and the crawler files are asked for by every bot.
EXEMPT_404_PATH_PATTERNS = [
    r"^/static/",
    r"^/favicon",
    r"^/robots\.txt$",
    r"^/sitemap",
    r"^/dashboard/",
    r"^/api/",
]
EXEMPT_404_REGEX = re.compile("|".join(EXEMPT_404_PATH_PATTERNS), re.IGNORECASE)

# Search engines and AI answer engines follow old links too, and a dead link must
# never shut them out. A scanner that claims to be one escapes the 404 count only;
# an attack signal still blocks it.
CRAWLERS = (
    "googlebot",
    "bingbot",
    "applebot",
    "duckduckbot",
    "yandexbot",
    "baiduspider",
    "gptbot",
    "oai-searchbot",
    "chatgpt-user",
    "claudebot",
    "claude-searchbot",
    "perplexitybot",
)


def is_crawler(request):
    agent = request.META.get("HTTP_USER_AGENT", "").lower()
    return any(name in agent for name in CRAWLERS)


# Paths only attack tools ask for. A request for one blocks the address at once for 12
# months, so each is anchored to where tools ask for it, and a test proves that no page,
# file or route of this site matches one: a pattern that matched inside a blog address
# would lock a reader out for a year.
ATTACK_PATH_PATTERNS = [
    r"\.php\d?$",  # nothing here is PHP
    r"^/(wp-|wordpress|xmlrpc)",
    r"/\.(env|git|svn|hg|aws|ssh|htaccess|htpasswd|ds_store)(/|$|\.)",
    r"^/(phpmyadmin|pma|myadmin|mysqladmin|adminer|dbadmin|sqlmanager)(/|$)",
    r"^/(administrator|joomla|drupal|magento)(/|$)",
    r"^/(cgi-bin|vendor/phpunit|actuator|manager/html|solr|jenkins|struts)(/|$)",
    r"^/(shell|webshell|backdoor|c99|r57)(\.|/|$)",
    r"^/(web\.config|config\.(json|yml|yaml|ini))$",
]
ATTACK_PATH_REGEX = re.compile("|".join(ATTACK_PATH_PATTERNS), re.IGNORECASE)

SCAN_LIMIT = 20  # different missing paths ...
SCAN_WINDOW = 5 * 60  # ... within this many seconds

# Answered for a blocked address too, so that a block can never look like an
# outage to whatever monitors the service.
HEALTH_CHECK_PATHS = ("/healthz", "/api/v1/health/")


def is_attack(request) -> bool:
    """A known scanner path, or a POST to the admin a hosted site keeps hidden: where the
    admin lives elsewhere (ATTACK_SIGNAL_ADMIN_PREFIX, respectlytics.com's settings), only a
    tool posts to /admin. The community edition's admin is /admin itself, so it sets none."""
    if ATTACK_PATH_REGEX.search(request.path):
        return True
    prefix = getattr(settings, "ATTACK_SIGNAL_ADMIN_PREFIX", None)
    return bool(prefix) and request.method == "POST" and request.path.startswith(prefix)


class SecurityMiddleware(MiddlewareMixin):
    """
    The door (loheden-security, "Client address, bans and rate limits"):

    - a blocked address is refused, and told so;
    - an attack signal blocks the address at once for 12 months;
    - 20 different missing pages within 5 minutes block it for 24 hours, longer on repeat;
    - 10 refused API keys within 15 minutes block it for an hour (throttling.py).

    The health answer comes before all of it. The blocks themselves are analytics/blocks.py.
    """

    def process_request(self, request):
        if getattr(settings, "TESTING", False):
            return None
        if request.path in HEALTH_CHECK_PATHS:
            return None

        ip = get_client_ip(request)
        if settings.DEBUG and ip in ("127.0.0.1", "localhost", "::1"):
            return None

        blocked = active_block(ip)
        if blocked is not None:
            logger.info("[SECURITY] Refused a blocked address (%s)", blocked.kind)
            refused(ip, blocked)
            return self._blocked_response(request, ip)

        if is_attack(request):
            # The address every Worker shares, and the server's own, are refused one request
            # at a time like anyone's, but never blocked (analytics/blocks.py).
            block(ip, ATTACK, f"{request.method} {request.path[:80]}")
            return self._blocked_response(request, ip)

        return None

    def process_response(self, request, response):
        ip = get_client_ip(request)

        if response.status_code == 404 and not getattr(settings, "TESTING", False):
            if self._count_missing(request, ip):
                return self._blocked_response(request, ip)

        if response.status_code == 401:
            app_key = self._extract_app_key(request)
            if track_failed_auth_attempt(request, app_key):
                logger.error("[SECURITY] Blocked an address for repeated refused API keys")
            else:
                logger.warning(f"[SECURITY] Refused API key: {app_key}")

        if response.status_code >= 500:
            logger.error(f"[SECURITY] Server error {response.status_code} for {request.path}")

        return response

    def _count_missing(self, request, ip) -> bool:
        """Count a missing page toward a scan. Returns whether this one blocked the address.
        Fails open if the cache is unreachable."""
        if settings.DEBUG and ip in ("127.0.0.1", "localhost", "::1"):
            return False
        if EXEMPT_404_REGEX.search(request.path) or is_crawler(request) or not blockable(ip):
            return False
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return False  # a signed-in customer following an old link is no scanner
        try:
            counter = f"missing:{address_key(ip)}"
            paths = cache.get(counter, set())
            paths.add(request.path[:200])
            if len(paths) < SCAN_LIMIT:
                cache.set(counter, paths, SCAN_WINDOW)
                return False
            cache.delete(counter)
        except Exception:
            logger.warning("[SECURITY] Cache unavailable during 404 counting, failing open")
            return False
        reason = f"{len(paths)} missing pages within {SCAN_WINDOW // 60} minutes"
        return block(ip, SCAN, reason) is not None

    def _blocked_response(self, request, ip):
        """
        Return a clear "You are blocked" response for banned IPs.

        This is shown AFTER the user is banned (not during stealth 404 phase).
        Uses a minimal self-contained HTML page to avoid template rendering issues.
        """
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>Blocked - Respectlytics</title>
    <link rel="stylesheet" href="/static/css/fonts.css">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Schibsted Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI',
                Roboto, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #f8fafc;
        }
        .container {
            text-align: center;
            padding: 2rem;
            max-width: 500px;
        }
        .code {
            font-size: 8rem;
            font-weight: 900;
            color: rgba(245, 158, 11, 0.2);
            line-height: 1;
            margin-bottom: 1rem;
        }
        .icon { font-size: 4rem; margin-bottom: 1.5rem; }
        h1 {
            font-size: 2.5rem;
            font-weight: 900;
            margin-bottom: 1rem;
            letter-spacing: -0.025em;
        }
        p {
            font-size: 1.125rem;
            color: #94a3b8;
            line-height: 1.6;
            margin-bottom: 2rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="code">403</div>
        <div class="icon">&#128683;</div>
        <h1>Blocked</h1>
        <p>Your IP address has been blocked due to suspicious activity.</p>
    </div>
</body>
</html>"""
        return HttpResponseForbidden(html, content_type="text/html; charset=utf-8")

    def _extract_app_key(self, request):
        """Extract app_key from various sources for logging"""
        # Check header
        app_key = request.META.get("HTTP_X_APP_KEY")
        if app_key:
            return app_key[:8] + "..."  # Only log first 8 chars for security

        # Check query params
        app_key = request.GET.get("app_key")
        if app_key:
            return app_key[:8] + "..."

        # Check body (for POST/PUT)
        if hasattr(request, "data") and isinstance(request.data, dict):
            app_key = request.data.get("app_key")
            if app_key:
                return app_key[:8] + "..."

        return "unknown"


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Log all API requests for monitoring and analytics.
    Can be disabled in production if performance is a concern.

    NOTE: IPs are intentionally NOT logged here to match our privacy stance.
    IPs are only logged by the security logger (legitimate interest) and
    for slow requests (>5s) for operational troubleshooting.
    """

    def process_request(self, request):
        """Log incoming requests (no IP — privacy by design)"""
        if request.path.startswith("/api/"):
            logger.info(f"API Request: {request.method} {request.path}")
        return None

    def process_response(self, request, response):
        """Log request completion with status"""
        if request.path.startswith("/api/"):
            logger.info(
                f"API Response: {request.method} {request.path} - Status {response.status_code}"
            )
        return response


class PerformanceMonitoringMiddleware(MiddlewareMixin):
    """
    Monitor API request performance and log slow requests.
    Helps identify performance bottlenecks and optimization opportunities.
    """

    def process_request(self, request):
        """Record request start time"""
        import time

        request._start_time = time.time()
        return None

    def process_response(self, request, response):
        """Log slow API requests (>5 seconds)"""
        import time

        # Only monitor API requests
        if not request.path.startswith("/api/"):
            return response

        # Calculate request duration
        if hasattr(request, "_start_time"):
            duration = time.time() - request._start_time

            # Log slow API requests (no IP — privacy by design)
            if duration > 5:
                logger.warning(
                    f"Slow API request: {request.method} {request.path} | "
                    f"duration={duration:.2f}s | status={response.status_code}"
                )

        return response


# =============================================================================
# SEC-014: Content Security Policy (CSP) and Permissions-Policy Headers
# =============================================================================


class CSPMiddleware(MiddlewareMixin):
    """
    Add Content-Security-Policy and Permissions-Policy headers to all responses.

    This protects against XSS attacks by whitelisting allowed content sources,
    and restricts access to sensitive browser APIs.

    CSP Policy:
    - Allows scripts/styles from self and required CDNs
    - Uses 'unsafe-inline' for compatibility with existing inline scripts
    - Restricts frames to Stripe and Cloudflare Turnstile
    - Blocks object/embed elements

    Permissions-Policy:
    - Disables unused browser APIs (camera, microphone, geolocation, etc.)
    - Allows payment API for Stripe integration

    Only active in production (when DEBUG=False).
    """

    # Third-party origins the browser is allowed to reach.
    #
    # No asset CDN appears here. Every front-end library is vendored into
    # static/vendor/ and served from this domain, so jsDelivr, cdnjs and
    # cdn.redoc.ly were removed: an asset fetched from someone else's CDN hands
    # that CDN the visitor's IP, User-Agent and Referer before a consent banner
    # can render, and there is no Art. 28 processor agreement covering it.
    # Keeping them listed here would let a stray CDN <script> load unnoticed.
    #
    # What remains is functional third-party *services*, not assets: Stripe for
    # payment and Turnstile for the CAPTCHA challenge. No analytics script runs:
    # respectlytics.com counts its visits on its own server, so Simple Analytics,
    # allowed there until 2026-10-21, is gone.
    CDN_SCRIPTS = [
        "https://challenges.cloudflare.com",  # Cloudflare Turnstile
    ]

    CDN_STYLES = []

    CDN_CONNECT = [
        "https://api.stripe.com",  # Stripe API
    ]

    CDN_FRAMES = [
        "https://js.stripe.com",  # Stripe checkout iframe
        "https://challenges.cloudflare.com",  # Turnstile iframe
    ]

    def process_response(self, request, response):
        """Add security headers to response."""
        # Skip in development to avoid breaking hot reload, etc.
        if settings.DEBUG:
            return response

        # Skip for streaming responses (e.g., file downloads)
        if response.streaming:
            return response

        # Build CSP header. Sources are joined through a helper so that an empty
        # allow-list (style-src, now that no stylesheet comes from anywhere but
        # this domain) collapses cleanly instead of leaving a double space.
        def directive(name, *sources):
            return " ".join([name, *(s for s in sources if s)])

        csp_directives = [
            "default-src 'self'",
            directive("script-src", "'self'", *self.CDN_SCRIPTS, "'unsafe-inline'"),
            directive("style-src", "'self'", *self.CDN_STYLES, "'unsafe-inline'"),
            "img-src 'self' data: https:",
            "font-src 'self' data:",
            directive("connect-src", "'self'", *self.CDN_CONNECT),
            "worker-src 'self' blob:",
            directive("frame-src", "'self'", *self.CDN_FRAMES),
            "object-src 'none'",
            "base-uri 'self'",
            # A form's redirect counts as its action: the checkout and the portal answer with a
            # redirect to Stripe, which 'self' alone blocked (owner, 2026-10-24).
            "form-action 'self' https://checkout.stripe.com https://billing.stripe.com",
            "frame-ancestors 'none'",
        ]

        response["Content-Security-Policy"] = "; ".join(csp_directives)

        # Build Permissions-Policy header
        # Disable unused browser APIs, allow payment for Stripe
        permissions_policy = [
            "accelerometer=()",
            "camera=()",
            "geolocation=()",
            "gyroscope=()",
            "magnetometer=()",
            "microphone=()",
            "payment=(self)",
            "usb=()",
        ]

        response["Permissions-Policy"] = ", ".join(permissions_policy)

        return response

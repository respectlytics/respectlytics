from django.http import JsonResponse, Http404, HttpResponseForbidden, HttpResponsePermanentRedirect
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
from django.conf import settings
import logging
import re
from .throttling import is_ip_banned, track_failed_auth_attempt, get_client_ip

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
        if host.startswith('www.'):
            # Build the non-www URL with same path and query string
            new_host = host[4:]  # Remove 'www.'
            new_url = f"https://{new_host}{request.get_full_path()}"
            return HttpResponsePermanentRedirect(new_url)
        
        return None


# =============================================================================
# SEC-013: Path Scanning Detection Configuration
# =============================================================================

# Paths EXEMPT from 404 scanning detection
# These are legitimate paths where 404s happen during normal use
# (e.g., missing static files, authenticated dashboard usage, API endpoints)
EXEMPT_404_PATH_PATTERNS = [
    r'^/static/',          # Static files - may 404 during development/deployment
    r'^/favicon',          # Favicon requests
    r'^/robots\.txt$',     # Robots file
    r'^/sitemap',          # Sitemap files
    r'^/dashboard/',       # Dashboard pages - authenticated users browsing
    r'^/api/',             # API endpoints - handled by API-level auth/throttling
]

# Compile exempt patterns for performance
EXEMPT_404_REGEX = re.compile('|'.join(EXEMPT_404_PATH_PATTERNS), re.IGNORECASE)

# Known attack paths - these count toward the 404 limit and return 404 (not 403)
# Returning 404 instead of 403 avoids revealing that files exist
ATTACK_PATH_PATTERNS = [
    # PHP/WordPress/CMS probes
    r'\.php$',
    r'/wp-',
    r'/wordpress',
    r'/wp-admin',
    r'/wp-login',
    r'/wp-includes',
    r'/wp-content',
    r'/xmlrpc\.php',
    # Common exploit paths
    r'/phpmyadmin',
    r'/pma',
    r'/myadmin',
    r'/mysqladmin',
    r'/admin\.php',
    r'/administrator',
    r'/joomla',
    r'/drupal',
    r'/magento',
    # Sensitive file probes
    r'/\.env',
    r'/\.git',
    r'/\.htaccess',
    r'/\.htpasswd',
    r'/config\.php',
    r'/web\.config',
    r'/\.aws',
    r'/\.ssh',
    r'/\.svn',
    r'/\.hg',
    # Shell/backdoor probes
    r'/shell',
    r'/c99',
    r'/r57',
    r'/webshell',
    r'/backdoor',
    # Scanner signatures
    r'/actuator',
    r'/console',
    r'/manager/html',
    r'/solr',
    r'/jenkins',
    r'/struts',
    # Database admin tools
    r'/adminer',
    r'/dbadmin',
    r'/sqlmanager',
]

# Compile regex for performance
ATTACK_PATH_REGEX = re.compile('|'.join(ATTACK_PATH_PATTERNS), re.IGNORECASE)

# Suspicious path tracking settings (same for both 404s and attack paths)
MAX_SUSPICIOUS_ATTEMPTS = 10   # Max attempts before ban
SCAN_WINDOW_SECONDS = 600      # 10 minute window
SCAN_BAN_DURATION = 3600       # 1 hour ban


class SecurityMiddleware(MiddlewareMixin):
    """
    Security middleware to handle:
    - IP banning for repeated authentication failures
    - SEC-013: Path scanning detection and 404 rate limiting
    - Request logging for security events
    - Invalid API key tracking
    
    Security principle: Always return 404 for security blocks (not 403)
    to avoid revealing information about what exists.
    """
    
    def process_request(self, request):
        """
        Check if IP is banned and detect attack path probes.
        
        SEC-013: Track attack path probes and ban after threshold.
        Always returns 404 (never 403) to avoid information disclosure.
        """
        # Skip security checks during tests
        if getattr(settings, 'TESTING', False):
            return None
        
        ip = get_client_ip(request)
        
        # Skip localhost in development
        if settings.DEBUG and ip in ('127.0.0.1', 'localhost', '::1'):
            return None
            
        # Check if IP is already banned - show clear blocked message
        if is_ip_banned(request):
            logger.warning(f"[SECURITY] Blocked request from banned IP: {ip}")
            return self._blocked_response(request, ip)
        
        # SEC-013: Check for attack path patterns - track like 404s, return 404
        path = request.path.lower()
        if ATTACK_PATH_REGEX.search(path):
            is_banned = self._track_attack_path(ip, path)
            if is_banned:
                logger.warning(f"[SECURITY] IP {ip} banned for excessive attack path probes")
                return self._blocked_response(request, ip)
            # Return 404 for attack paths (don't reveal they're detected) until banned
            raise Http404("Page not found")
        
        return None
    
    def process_response(self, request, response):
        """
        Log security events and track 404s for scanning detection.
        
        SEC-013: Track 404 responses and ban excessive scanners.
        Exempt authenticated users and static file paths from 404 banning.
        """
        ip = get_client_ip(request)
        
        # SEC-013: Track 404 responses for path scanning detection
        if response.status_code == 404:
            # Skip localhost in development
            if not (settings.DEBUG and ip in ('127.0.0.1', 'localhost', '::1')):
                # Skip exempt paths (static files, dashboard, API, etc.)
                # These are not attack probes - just missing files or normal navigation
                if EXEMPT_404_REGEX.search(request.path):
                    pass  # Don't track these 404s as suspicious
                # Skip authenticated users - they're legitimate users, not scanners
                elif hasattr(request, 'user') and request.user and request.user.is_authenticated:
                    pass  # Authenticated users get much more lenient treatment
                else:
                    # Track as potential path scanning (unauthenticated, non-exempt paths)
                    is_banned = self._track_404(ip, request.path)
                    if is_banned:
                        logger.warning(f"[SECURITY] IP {ip} banned for excessive 404s (path scanning)")
                        # Return blocked page immediately when threshold is reached
                        return self._blocked_response(request, ip)
        
        # Track failed authentication attempts (401 status)
        if response.status_code == 401:
            app_key = self._extract_app_key(request)
            
            # Track the failed attempt
            is_banned = track_failed_auth_attempt(request, app_key)
            
            if is_banned:
                logger.error(f"[SECURITY] IP {ip} banned due to repeated failed auth attempts")
            else:
                logger.warning(f"[SECURITY] Failed auth attempt from IP: {ip}, app_key: {app_key}")
        
        # Log suspicious activity (too many errors)
        if response.status_code >= 500:
            logger.error(f"[SECURITY] Server error {response.status_code} for IP: {ip}, path: {request.path}")
        
        return response
    
    def _track_404(self, ip, path):
        """
        SEC-013: Track 404 attempts and ban if threshold exceeded.
        
        Returns True if IP was banned, False otherwise.
        Fails open if cache/DB is unreachable.
        """
        try:
            cache_key = f'404_count:{ip}'
            count = cache.get(cache_key, 0) + 1
            cache.set(cache_key, count, SCAN_WINDOW_SECONDS)
            
            logger.info(f"[SECURITY] 404 attempt #{count} from {ip}: {path}")
            
            if count >= MAX_SUSPICIOUS_ATTEMPTS:
                # Ban the IP
                cache.set(f'banned:{ip}', True, SCAN_BAN_DURATION)
                logger.warning(f"[SECURITY] IP {ip} banned after {count} 404s in {SCAN_WINDOW_SECONDS}s")
                
                # SEC-007: IP banned alert emails disabled (too noisy in production)
                # Bans are still logged above - check logs/security.log
                
                return True
        except Exception:
            logger.warning(f"[SECURITY] Cache unavailable during 404 tracking for IP: {ip} \u2014 failing open")
        return False
    
    def _track_attack_path(self, ip, path):
        """
        SEC-013: Track attack path probes and ban if threshold exceeded.
        
        Attack paths (like /.env, /wp-admin) are tracked separately from 404s
        but use the same threshold. This allows legitimate 404s while still
        catching attackers who specifically probe for vulnerabilities.
        
        Returns True if IP was banned, False otherwise.
        Fails open if cache/DB is unreachable.
        """
        try:
            cache_key = f'attack_path_count:{ip}'
            count = cache.get(cache_key, 0) + 1
            cache.set(cache_key, count, SCAN_WINDOW_SECONDS)
            
            logger.warning(f"[SECURITY] Attack path probe #{count} from {ip}: {path}")
            
            if count >= MAX_SUSPICIOUS_ATTEMPTS:
                # Ban the IP
                cache.set(f'banned:{ip}', True, SCAN_BAN_DURATION)
                logger.error(f"[SECURITY] IP {ip} banned after {count} attack path probes")
                
                # SEC-007: IP banned alert emails disabled (too noisy in production)
                
                return True
        except Exception:
            logger.warning(f"[SECURITY] Cache unavailable during attack path tracking for IP: {ip} \u2014 failing open")
        return False
    
    def _blocked_response(self, request, ip):
        """
        Return a clear "You are blocked" response for banned IPs.
        
        This is shown AFTER the user is banned (not during stealth 404 phase).
        Uses a minimal self-contained HTML page to avoid template rendering issues.
        """
        html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>Blocked - Respectlytics</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
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
        .btn {
            display: inline-block;
            background: #334155;
            color: #cbd5e1;
            text-decoration: none;
            padding: 1rem 2rem;
            border-radius: 0.75rem;
            font-weight: 600;
            font-size: 1rem;
            border: 2px solid #475569;
            transition: all 0.2s;
        }
        .btn:hover {
            background: #475569;
            transform: translateY(-2px);
        }
        .help {
            margin-top: 2rem;
            color: #64748b;
            font-size: 0.875rem;
        }
        .help a {
            color: #a78bfa;
            text-decoration: none;
        }
        .help a:hover { color: #c4b5fd; }
    </style>
</head>
<body>
    <div class="container">
        <div class="code">403</div>
        <div class="icon">&#128683;</div>
        <h1>Blocked</h1>
        <p>Your IP address has been blocked due to suspicious activity.</p>
        <a href="/" class="btn">Go Home</a>
    </div>
</body>
</html>'''
        return HttpResponseForbidden(html, content_type='text/html; charset=utf-8')
    
    def _extract_app_key(self, request):
        """Extract app_key from various sources for logging"""
        # Check header
        app_key = request.META.get('HTTP_X_APP_KEY')
        if app_key:
            return app_key[:8] + '...'  # Only log first 8 chars for security
        
        # Check query params
        app_key = request.GET.get('app_key')
        if app_key:
            return app_key[:8] + '...'
        
        # Check body (for POST/PUT)
        if hasattr(request, 'data') and isinstance(request.data, dict):
            app_key = request.data.get('app_key')
            if app_key:
                return app_key[:8] + '...'
        
        return 'unknown'


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
        if request.path.startswith('/api/'):
            logger.info(f"API Request: {request.method} {request.path}")
        return None
    
    def process_response(self, request, response):
        """Log request completion with status"""
        if request.path.startswith('/api/'):
            logger.info(f"API Response: {request.method} {request.path} - Status {response.status_code}")
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
        if not request.path.startswith('/api/'):
            return response
        
        # Calculate request duration
        if hasattr(request, '_start_time'):
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
    
    # CDN domains required for the application
    CDN_SCRIPTS = [
        'https://cdn.jsdelivr.net',      # Chart.js, Flatpickr
        'https://cdnjs.cloudflare.com',  # Prism.js syntax highlighting
        'https://cdn.redoc.ly',          # ReDoc API documentation
        'https://scripts.simpleanalyticscdn.com',  # Simple Analytics
        'https://challenges.cloudflare.com',  # Cloudflare Turnstile
    ]
    
    CDN_STYLES = [
        'https://cdn.jsdelivr.net',      # Flatpickr styles
    ]
    
    CDN_CONNECT = [
        'https://api.stripe.com',        # Stripe API
        'https://simpleanalytics.com',   # Simple Analytics
        'https://cdn.redoc.ly',          # ReDoc runtime assets
    ]
    
    CDN_FRAMES = [
        'https://js.stripe.com',         # Stripe checkout iframe
        'https://challenges.cloudflare.com',  # Turnstile iframe
    ]
    
    def process_response(self, request, response):
        """Add security headers to response."""
        # Skip in development to avoid breaking hot reload, etc.
        if settings.DEBUG:
            return response
        
        # Skip for streaming responses (e.g., file downloads)
        if response.streaming:
            return response
        
        # Build CSP header
        csp_directives = [
            "default-src 'self'",
            f"script-src 'self' {' '.join(self.CDN_SCRIPTS)} 'unsafe-inline'",
            f"style-src 'self' {' '.join(self.CDN_STYLES)} 'unsafe-inline'",
            "img-src 'self' data: https:",
            "font-src 'self' data:",
            f"connect-src 'self' {' '.join(self.CDN_CONNECT)}",
            "worker-src 'self' blob:",
            f"frame-src 'self' {' '.join(self.CDN_FRAMES)}",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
        
        response['Content-Security-Policy'] = '; '.join(csp_directives)
        
        # Build Permissions-Policy header
        # Disable unused browser APIs, allow payment for Stripe
        permissions_policy = [
            'accelerometer=()',
            'camera=()',
            'geolocation=()',
            'gyroscope=()',
            'magnetometer=()',
            'microphone=()',
            'payment=(self)',
            'usb=()',
        ]
        
        response['Permissions-Policy'] = ', '.join(permissions_policy)
        
        return response

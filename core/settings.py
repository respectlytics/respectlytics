"""
Django settings for Respectlytics Community Edition.

This is the open-source edition settings file. It removes all SaaS-specific
configuration (billing, website, tools, demo) and provides sensible defaults
for self-hosted deployments.

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.2/ref/settings/
"""

import sys
from pathlib import Path
from typing import Any

import environ
from whitenoise.storage import CompressedManifestStaticFilesStorage

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Initialize environ
env: Any = environ.Env(
    DEBUG=(bool, True),
    REGISTRATION_CLOSED=(bool, False),
)

# Read .env file
environ.Env.read_env(BASE_DIR / ".env")

# =============================================================================
# Respectlytics Edition
# =============================================================================
RESPECTLYTICS_EDITION = "community"

# User Registration Control
# When True, the signup page shows a "registration closed" message instead of the form
# Useful for pre-launch or maintenance periods
REGISTRATION_CLOSED = env("REGISTRATION_CLOSED")

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
# IMPORTANT: Change this in production!
# Generate with:
#   python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
SECRET_KEY = env("SECRET_KEY", default="change-me-in-production-generate-a-random-string")
# Earlier keys, still accepted for signed values while a new SECRET_KEY settles in
# (comma-separated, newest first). Rotating: move the old key here, set the new one,
# remove it here once sessions and links signed with it have expired.
SECRET_KEY_FALLBACKS = env.list("SECRET_KEY_FALLBACKS", default=[])

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")
TESTING = "test" in sys.argv or "pytest" in sys.modules

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "0.0.0.0"])

# Security settings
# SSL redirect is opt-in via SECURE_SSL=True (for deployments behind HTTPS reverse proxy)
# Docker Compose runs plain HTTP, so this defaults to False
SECURE_SSL = env.bool("SECURE_SSL", default=False)

if SECURE_SSL:
    # Force HTTPS
    SECURE_SSL_REDIRECT = True
    # A health check may ask the container itself over plain HTTP.
    SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # HSTS (HTTP Strict Transport Security)
    # Tells browsers to only use HTTPS for this site
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # Trust X-Forwarded-Proto header from reverse proxy (nginx/apache)
    # This tells Django the request is secure when proxy forwards HTTPS
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
else:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

# Always enable these regardless of SSL
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# The test suite must not depend on how SECURE_SSL happens to resolve on the machine
# running it. With the SSL redirect on, every test-client request becomes a 301 and the
# suite fails wholesale with "301 != 200", which says nothing about the code. TESTING is
# only ever true under `manage.py test` or pytest, so production is untouched by this.
if TESTING:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_yasg",
    # SEC-009: Django OTP for admin 2FA (optional, controlled by ADMIN_REQUIRE_OTP)
    "django_otp",
    "django_otp.plugins.otp_totp",  # Time-based OTP (Google Authenticator)
    "django_otp.plugins.otp_static",  # Backup/recovery codes
    "analytics",  # Core analytics API
    "conversion",  # Conversion Intelligence API
    "dashboard",  # Authenticated dashboard UI
    "users",  # User authentication
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Serve static files with gunicorn
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",  # SEC-009: Admin 2FA support
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "analytics.middleware.SecurityMiddleware",
    "analytics.middleware.RequestLoggingMiddleware",
    "analytics.middleware.PerformanceMonitoringMiddleware",  # Monitor slow API requests
]

ROOT_URLCONF = "core.urls"

# A refused form opens the sign-in pages again or shows the site's own 403 (core/csrf.py),
# never Django's bare page.
CSRF_FAILURE_VIEW = "core.csrf.csrf_failure"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # Project-level shared templates
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"


# =============================================================================
# Database
# =============================================================================
# PostgreSQL is REQUIRED. We use django.contrib.postgres aggregates (ArrayAgg).
# SQLite is NOT supported and will crash.

TEST_DATABASE_URL = env("DATABASE_URL_TEST", default=None)

if TESTING and TEST_DATABASE_URL:
    DATABASES = {"default": env.db("DATABASE_URL_TEST")}
elif DEBUG:
    DATABASES = {
        "default": env.db(
            "DATABASE_URL_DEV",
            default=env("DATABASE_URL", default="postgres://localhost/respectlytics"),
        )
    }
else:
    DATABASES = {"default": env.db("DATABASE_URL")}

# SSL for production databases (e.g., managed PostgreSQL services)
# Enable with DATABASE_SSL=True when using managed PostgreSQL (e.g., AWS RDS, DigitalOcean)
# Docker Compose local PostgreSQL does NOT support SSL, so this defaults to False
if env.bool("DATABASE_SSL", default=False):
    DATABASES["default"]["OPTIONS"] = {
        "sslmode": "require",
    }

    _db_port = str(DATABASES["default"].get("PORT", ""))
    _using_digitalocean_pool = _db_port == "25061"
    if not _using_digitalocean_pool:
        DATABASES["default"]["OPTIONS"]["options"] = "-c search_path=public"

# CONN_MAX_AGE: reuse a connection for 60 seconds instead of opening one per request.
# CONN_HEALTH_CHECKS: ping a reused connection first and reconnect if the server closed
#   it (a restart of the database), instead of failing the request.
DATABASES["default"]["CONN_MAX_AGE"] = 60  # 60 seconds
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# Required when using transaction-mode PostgreSQL connection pools.
# Export views use QuerySet.iterator(), and server-side cursors cannot safely
# span pooled transactions.
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

# Test database
if TEST_DATABASE_URL:
    DATABASES["default"]["TEST"] = {
        "NAME": env.db("DATABASE_URL_TEST")["NAME"],
    }

# Every run on fresh databases, a crashed run's leftover dropped without asking.
TEST_RUNNER = "core.test_runner.FreshDatabaseTestRunner"


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"

# Serve project-level static assets (e.g., /static/geojson) in development
# This allows accessing files placed under BASE_DIR/static via /static/
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# Target directory for collectstatic in production environments
STATIC_ROOT = BASE_DIR / "staticfiles"


class ForgivingManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Manifest storage that will not take the site down over a missing file.

    The manifest backend is what earns static files a far-future cache header:
    collectstatic writes every file a second time under a content-hashed name,
    so the URL changes whenever the bytes change and WhiteNoise can serve the
    hashed copies `immutable` for a year instead of the 60 seconds a plain,
    un-hashed filename has to settle for.

    With Django's default `manifest_strict = True`, a `{% static %}` pointing at
    a file that does not exist stops being a broken image and becomes a 500 for
    the whole page. Turning it off restores exactly the old behaviour for that
    case - the URL is emitted unhashed and 404s - while every file that does
    exist still gets its hashed, immutable URL.
    """

    manifest_strict = False


STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        # Plain storage under test: the manifest only exists after a
        # collectstatic run, and without this every {% static %} in every
        # template test fails on a missing manifest rather than on the code
        # under test.
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if TESTING
            else "core.settings.ForgivingManifestStaticFilesStorage"
        ),
    },
}

# Keep the un-hashed copy of every file alongside the hashed one. Explicit
# rather than relying on the default, because a handful of assets are fetched
# from JavaScript by their literal path - /static/geojson/countries.geojson in
# the globe code - and never pass through {% static %} to pick up a hash. Those
# keep the short cache header; everything a template references gets the
# immutable one.
WHITENOISE_KEEP_ONLY_HASHED_FILES = False

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# REST Framework settings
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        # BrowsableAPIRenderer removed - use Swagger/ReDoc for API exploration
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # The dashboard, signed in; only sending events takes the app key alone.
        "analytics.authentication.AppOwnerSessionAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Allow ?format parameter for schema endpoints, but renamed to avoid conflicts
    # with our export endpoint's ?format=csv parameter
    "URL_FORMAT_OVERRIDE": "format",
    "UNAUTHENTICATED_USER": None,
}

# Export safeguards (limits are configurable via .env)
# Default: allow up to 100k events per export and at most 90 days per request.
EXPORT_MAX_EVENTS = int(env("EXPORT_MAX_EVENTS", default=100000))
EXPORT_MAX_DAYS = int(env("EXPORT_MAX_DAYS", default=90))

# Logging configuration for security monitoring
# - Development (DEBUG=True): Logs to both console AND file (logs/security.log)
# - Production (DEBUG=False): Logs to console only; RedactPersonalDataFilter keeps
#   addresses out of it
#
# In containerized environments, file logs are ephemeral and inaccessible.
# Console output is automatically captured by the platform's log aggregation.

_logging_handlers = {
    "console": {
        "class": "logging.StreamHandler",
        "formatter": "verbose",
        "filters": ["sanitize_app_key", "redact_personal_data"],
    },
}

# Only add file handler in development
if DEBUG:
    # Ensure logs directory exists for local development
    if not (BASE_DIR / "logs").exists():
        (BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)

    _logging_handlers["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": BASE_DIR / "logs" / "security.log",
        "formatter": "verbose",
        "filters": ["sanitize_app_key", "redact_personal_data"],
        "maxBytes": 10485760,  # 10 MB
        "backupCount": 5,  # Keep 5 backup files (50 MB total max)
    }

# Analytics logger uses file handler only in development
_analytics_handlers = ["console", "file"] if DEBUG else ["console"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "sanitize_app_key": {
            "()": "analytics.logging_filters.SanitizeAppKeyFilter",
        },
        # No email or IP address in the log: each becomes a keyed code.
        "redact_personal_data": {
            "()": "analytics.logging_filters.RedactPersonalDataFilter",
        },
    },
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": _logging_handlers,
    "loggers": {
        "analytics": {
            "handlers": _analytics_handlers,
            "level": "INFO",
            "propagate": False,
        },
        # Sanitize Django's default server logging
        "django.server": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # Sanitize Django's basehttp logger (the one that logs requests)
        "django.server.basehttp": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Email: printed to the console unless EMAIL_BACKEND names another backend. For real
# delivery set it to django.core.mail.backends.smtp.EmailBackend, and the EMAIL_* variables
# (.env.example) become the options of Django's one mailer.
_mail_backend = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
_mail_options = {}
if "smtp" in _mail_backend.lower():
    _mail_options = {
        "host": env("EMAIL_HOST", default="localhost"),
        "port": env.int("EMAIL_PORT", default=587),
        "use_tls": env.bool("EMAIL_USE_TLS", default=True),
        "username": env("EMAIL_HOST_USER", default=""),
        "password": env("EMAIL_HOST_PASSWORD", default=""),
    }
MAILERS = {"default": {"BACKEND": _mail_backend, "OPTIONS": _mail_options}}

# Email addresses (use environment variables for flexibility)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Respectlytics <noreply@localhost>")
EMAIL_REPLY_TO = env("EMAIL_REPLY_TO", default="noreply@localhost")
# This server's own address, for the links in security emails, and who receives the
# admin security alerts (account lockouts, banned addresses). With no address set,
# no admin alert is sent.
SITE_URL = env("SITE_URL", default="http://localhost:8080")
SECURITY_CONTACT_EMAIL = env("SECURITY_CONTACT_EMAIL", default="")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

ADMINS = []
MANAGERS = ADMINS
# The mail of a failed request carries no address, cookie, form field or email of the person
# who made it (analytics/error_reports.py).
DEFAULT_EXCEPTION_REPORTER_FILTER = "analytics.error_reports.PrivateExceptionReporterFilter"
DEFAULT_EXCEPTION_REPORTER = "analytics.error_reports.PrivateExceptionReporter"

# Authentication URLs
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/login/"

# Swagger/OpenAPI Documentation Settings
# drf-yasg renderer formats are 'json' / 'yaml' with no leading dot; the schema
# URLs in core/urls.py keep the dot outside the captured format.
SWAGGER_USE_COMPAT_RENDERERS = False

SWAGGER_SETTINGS = {
    "USE_SESSION_AUTH": False,  # Hide session auth (Django Login button)
    "SECURITY_DEFINITIONS": {
        "App API Key": {
            "type": "apiKey",
            "name": "X-App-Key",
            "in": "header",
            "description": (
                "App API Key sent via the X-App-Key header.\n\n"
                "• In Swagger UI: click the Authorize button and paste only the UUID value.\n"
                "• In your app or curl: send header X-App-Key: App_API_Key.\n\n"
            ),
        }
    },
    "SUPPORTED_SUBMIT_METHODS": ["get", "post"],  # Only show relevant methods
    "DOC_EXPANSION": "list",  # Show endpoints collapsed by default
    "DEEP_LINKING": True,
    "DISPLAY_OPERATION_ID": False,  # Hide operation IDs
    "DEFAULT_MODEL_RENDERING": "model",  # Show models collapsed
}

# ReDoc settings
REDOC_SETTINGS = {
    "LAZY_RENDERING": False,
}

# Test settings - disable throttling during tests
if TESTING:
    REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {}


# =============================================================================
# PERF-006: Database Caching Configuration
# =============================================================================
# Use Django's database cache backend for caching expensive dashboard queries.
# No external Redis/Memcached required - uses the existing PostgreSQL database.
#
# Cache table must be created with: python manage.py createcachetable
#
# TTL recommendations:
# - filter_options: 5 min (changes rarely)
# - summary/counts: 1-2 min (dashboard data, frequent updates)
# - funnel results: 2 min (expensive to compute)
# - conversion stats: 2 min (expensive to compute)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
        "TIMEOUT": 120,  # Default 2 minutes
        "OPTIONS": {
            "MAX_ENTRIES": 1000,  # Max cached items before culling
            "CULL_FREQUENCY": 3,  # Remove 1/3 of entries when MAX_ENTRIES reached
        },
    }
}

# Cache TTL settings (seconds)
CACHE_TTL_FILTER_OPTIONS = 600  # 10 minutes - filter options (event types, countries) rarely change
CACHE_TTL_SUMMARY = 120  # 2 minutes - summary counts update with new events
CACHE_TTL_FUNNEL = 300  # 5 minutes - funnel analysis is expensive, historical data
CACHE_TTL_CONVERSION = 300  # 5 minutes - conversion/behavior/retention stats are expensive

# Globe Stats Performance Settings
GLOBE_STATS_CACHE_TTL = 900  # 15 minutes - globe visualization doesn't require real-time precision
GLOBE_STATS_QUERY_TIMEOUT = 30  # 30 seconds - query timeout in seconds
GLOBE_STATS_SLOW_QUERY_THRESHOLD = 2  # 2 seconds - log queries slower than this


# =============================================================================
# SEC-002: Rate Limiting Configuration
# =============================================================================
# Uses django-ratelimit with database cache backend.
# Protects login, registration, and password reset from brute force attacks.

RATELIMIT_ENABLE = True
RATELIMIT_USE_CACHE = "default"
# Don't use a custom view - we handle rate limiting inline for better UX

# Who a request came from, for every limit, ban, geolocation and log
# (analytics/client_ip.py). A self-hosted server trusts no header naming the
# visitor unless the edge in front of it sets and overwrites that header, so
# TRUSTED_CLIENT_IP_HEADER is empty by default; behind Cloudflare it is
# CF-Connecting-IP. Published directly, or behind your own nginx or Caddy,
# leave it empty: the address your proxy appends is read without it.
TRUSTED_CLIENT_IP_HEADERS = tuple(
    "HTTP_" + header.strip().upper().replace("-", "_")
    for header in env.list("TRUSTED_CLIENT_IP_HEADER", default=[])
    if header.strip()
)
RATELIMIT_IP_META_KEY = "analytics.client_ip.get_client_ip"


# =============================================================================
# SEC-009: Django OTP Configuration (Admin Two-Factor Authentication)
# =============================================================================
# Set to True to require OTP for admin access (recommended for production)
ADMIN_REQUIRE_OTP = env.bool("ADMIN_REQUIRE_OTP", default=False)

# Issuer name shown in authenticator apps
OTP_TOTP_ISSUER = "Respectlytics"

# Hide sensitive data (keys, QR codes) in admin when in production
OTP_ADMIN_HIDE_SENSITIVE_DATA = not DEBUG

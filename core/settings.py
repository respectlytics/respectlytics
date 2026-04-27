"""
Django settings for Respectlytics Community Edition.

This is the open-source edition settings file. It removes all SaaS-specific
configuration (billing, website, tools, demo) and provides sensible defaults
for self-hosted deployments.

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.2/ref/settings/
"""

from pathlib import Path
from typing import Any
import environ
import sys

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Initialize environ
env: Any = environ.Env(
    DEBUG=(bool, True),
    REGISTRATION_CLOSED=(bool, False),
)

# Read .env file
environ.Env.read_env(BASE_DIR / '.env')

# =============================================================================
# Respectlytics Edition
# =============================================================================
RESPECTLYTICS_EDITION = 'community'

# User Registration Control
# When True, the signup page shows a "registration closed" message instead of the form
REGISTRATION_CLOSED = env('REGISTRATION_CLOSED')

# =============================================================================
# Security Settings
# =============================================================================

# IMPORTANT: Change this in production!
# Generate with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
SECRET_KEY = env('SECRET_KEY', default='change-me-in-production-generate-a-random-string')

DEBUG = env('DEBUG')

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1', '0.0.0.0'])

# Security settings
# SSL redirect is opt-in via SECURE_SSL=True (for deployments behind HTTPS reverse proxy)
# Docker Compose runs plain HTTP, so this defaults to False
SECURE_SSL = env.bool('SECURE_SSL', default=False)

if SECURE_SSL:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
else:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

# Always enable these regardless of SSL
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'


# =============================================================================
# Application definition
# =============================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'drf_yasg',
    # SEC-009: Django OTP for admin 2FA (optional, controlled by ADMIN_REQUIRE_OTP)
    'django_otp',
    'django_otp.plugins.otp_totp',
    'django_otp.plugins.otp_static',
    # Core apps
    'analytics',
    'conversion',
    'dashboard',
    'users',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django_otp.middleware.OTPMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'analytics.middleware.SecurityMiddleware',
    'analytics.middleware.RequestLoggingMiddleware',
    'analytics.middleware.PerformanceMonitoringMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'


# =============================================================================
# Database
# =============================================================================
# PostgreSQL is REQUIRED. We use django.contrib.postgres aggregates (ArrayAgg).
# SQLite is NOT supported and will crash.

if DEBUG:
    DATABASES = {
        'default': env.db('DATABASE_URL_DEV', default=env('DATABASE_URL', default='postgres://localhost/respectlytics'))
    }
else:
    DATABASES = {
        'default': env.db('DATABASE_URL')
    }

# SSL for production databases (e.g., managed PostgreSQL services)
# Enable with DATABASE_SSL=True when using managed PostgreSQL (e.g., AWS RDS, DigitalOcean)
# Docker Compose local PostgreSQL does NOT support SSL, so this defaults to False
if env.bool('DATABASE_SSL', default=False):
    DATABASES['default']['OPTIONS'] = {
        'sslmode': 'require',
        'options': '-c search_path=public',
    }

# Connection resilience
DATABASES['default']['CONN_MAX_AGE'] = 60  # 60 seconds
DATABASES['default']['CONN_HEALTH_CHECKS'] = True

# Test database
TEST_DATABASE_URL = env('DATABASE_URL_TEST', default=None)
if TEST_DATABASE_URL:
    DATABASES['default']['TEST'] = {
        'NAME': env.db('DATABASE_URL_TEST')['NAME'],
    }

TEST_RUNNER = 'core.test_runner.KeepDbTestRunner'


# =============================================================================
# Password validation
# =============================================================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# =============================================================================
# Internationalization
# =============================================================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# =============================================================================
# Static files
# =============================================================================
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# =============================================================================
# REST Framework
# =============================================================================
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'analytics.authentication.AppKeyAuthentication',
    ],
    'URL_FORMAT_OVERRIDE': 'format',
    'UNAUTHENTICATED_USER': None,
}

# Export safeguards
EXPORT_MAX_EVENTS = int(env('EXPORT_MAX_EVENTS', default=100000))
EXPORT_MAX_DAYS = int(env('EXPORT_MAX_DAYS', default=90))


# =============================================================================
# Logging
# =============================================================================
_logging_handlers = {
    'console': {
        'class': 'logging.StreamHandler',
        'formatter': 'verbose',
        'filters': ['sanitize_app_key'],
    },
}

if DEBUG:
    if not (BASE_DIR / 'logs').exists():
        (BASE_DIR / 'logs').mkdir(parents=True, exist_ok=True)
    _logging_handlers['file'] = {
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': BASE_DIR / 'logs' / 'security.log',
        'formatter': 'verbose',
        'filters': ['sanitize_app_key'],
        'maxBytes': 10485760,
        'backupCount': 5,
    }

_analytics_handlers = ['console', 'file'] if DEBUG else ['console']

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'sanitize_app_key': {
            'class': 'analytics.logging_filters.SanitizeAppKeyFilter',
        },
    },
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': _logging_handlers,
    'loggers': {
        'analytics': {
            'handlers': _analytics_handlers,
            'level': 'INFO',
            'propagate': False,
        },
        'django.server': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}


# =============================================================================
# Email Configuration
# =============================================================================
# Default: Console backend (prints emails to terminal output)
# Configure SMTP for real email delivery in production
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')

if 'smtp' in EMAIL_BACKEND.lower():
    EMAIL_HOST = env('EMAIL_HOST', default='localhost')
    EMAIL_PORT = env.int('EMAIL_PORT', default=587)
    EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
    EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
    EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')

DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='Respectlytics <noreply@localhost>')
EMAIL_REPLY_TO = env('EMAIL_REPLY_TO', default='noreply@localhost')
SERVER_EMAIL = DEFAULT_FROM_EMAIL

ADMINS = []
MANAGERS = ADMINS


# =============================================================================
# Authentication URLs
# =============================================================================
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'


# =============================================================================
# API Documentation (Swagger/ReDoc)
# =============================================================================
SWAGGER_SETTINGS = {
    'USE_SESSION_AUTH': False,
    'SECURITY_DEFINITIONS': {
        'App API Key': {
            'type': 'apiKey',
            'name': 'X-App-Key',
            'in': 'header',
            'description': (
                'App API Key sent via the X-App-Key header.\n\n'
                '• In Swagger UI: click the Authorize button and paste only the UUID value.\n'
                '• In your app or curl: send header X-App-Key: App_API_Key.\n\n'
            )
        }
    },
    'SUPPORTED_SUBMIT_METHODS': ['get', 'post'],
    'DOC_EXPANSION': 'list',
    'DEEP_LINKING': True,
    'DISPLAY_OPERATION_ID': False,
    'DEFAULT_MODEL_RENDERING': 'model',
}

REDOC_SETTINGS = {
    'LAZY_RENDERING': False,
}


# =============================================================================
# Test settings
# =============================================================================
TESTING = 'test' in sys.argv or 'pytest' in sys.modules
if TESTING:
    REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = []
    REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {}


# =============================================================================
# Caching (Database-backed)
# =============================================================================
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'django_cache',
        'TIMEOUT': 120,
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
            'CULL_FREQUENCY': 3,
        }
    }
}

CACHE_TTL_FILTER_OPTIONS = 600
CACHE_TTL_SUMMARY = 120
CACHE_TTL_FUNNEL = 300
CACHE_TTL_CONVERSION = 300

GLOBE_STATS_CACHE_TTL = 900
GLOBE_STATS_QUERY_TIMEOUT = 30
GLOBE_STATS_SLOW_QUERY_THRESHOLD = 2


# =============================================================================
# Rate Limiting
# =============================================================================
RATELIMIT_ENABLE = True
RATELIMIT_USE_CACHE = 'default'


# =============================================================================
# Admin OTP (Two-Factor Authentication)
# =============================================================================
# Set to True to require OTP for admin access (recommended for production)
ADMIN_REQUIRE_OTP = env.bool('ADMIN_REQUIRE_OTP', default=False)

OTP_TOTP_ISSUER = 'Respectlytics'
OTP_ADMIN_HIDE_SENSITIVE_DATA = not DEBUG

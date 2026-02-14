"""
URL configuration for Respectlytics Community Edition.

Clean URL config without website/tools/billing/demo apps.
"""
from django.urls import path, include, re_path
from django.views.generic import TemplateView, RedirectView
from django.contrib.auth import views as auth_views
from django.conf import settings
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from users.views import (
    register_view, verify_email, login_view, logout_view, registration_complete_view,
    resend_verification_email,
    account_view, account_profile_view,
    account_security_view,
    account_data_management_view,
    delete_account_view,
)
from users import views as users_views

# Admin: always use SecureAdminSite (provides security dashboard).
# OTP (2FA) is only enforced when ADMIN_REQUIRE_OTP=True.
from analytics.admin_security import security_admin_site
from django.contrib import admin
# Copy all registered models from the default admin to our custom admin
for model_cls, model_admin in admin.site._registry.items():
    security_admin_site.register(model_cls, model_admin.__class__)
admin_site = security_admin_site

# API Documentation - Public
public_schema_view = get_schema_view(
    openapi.Info(
        title="Respectlytics API",
        default_version='v1',
        description="""Privacy-first mobile analytics API — Community Edition.

## Getting Started

1. [Create an account](/register/) and set up your first app
2. Copy your **App API Key** (UUID) from the [Dashboard](/dashboard/)
3. Integrate with our SDKs or call the API directly

## Authentication

All API endpoints require the `X-App-Key` header with your App API Key:

```
X-App-Key: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

## Core Endpoints

- **POST /api/v1/events/** — Submit analytics events
- **GET /api/v1/events/summary/** — Retrieve event summary
- **GET /api/v1/events/geo-summary/** — Geographic distribution
- **GET /api/v1/events/funnel/** — Funnel analysis
- **GET /api/v1/events/event-types/** — List event types

## SDKs

Official SDKs handle authentication, batching, and offline support automatically:
- [Swift (iOS)](https://github.com/nickloheden/respectlytics-swift)
- [Kotlin (Android)](https://github.com/nickloheden/respectlytics-kotlin)
- [Flutter](https://github.com/nickloheden/respectlytics-flutter)
- [React Native](https://github.com/nickloheden/respectlytics-react-native)
""",
        license=openapi.License(name="AGPL-3.0"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    # Home: redirect to dashboard (login_required will redirect to login if needed)
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),

    # Admin
    path('admin/', admin_site.urls),

    # Authentication
    path('register/', register_view, name='register'),
    path('register/complete/', registration_complete_view, name='registration_complete'),
    path('resend-verification/', resend_verification_email, name='resend_verification'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('verify-email/<uidb64>/<token>/', verify_email, name='verify_email'),

    # Account Settings (3 tabs — no billing, no preferences)
    path('account/', account_view, name='account'),
    path('account/profile/', account_profile_view, name='account_profile'),
    path('account/security/', account_security_view, name='account_security'),
    path('account/data-management/', account_data_management_view, name='account_data_management'),
    path('account/delete/', delete_account_view, name='account_delete'),

    # Dashboard (authenticated views)
    path('dashboard/', include('dashboard.urls')),

    # Password Reset
    path('password-reset/', users_views.CustomPasswordResetView.as_view(
        template_name='users/auth/password_reset.html',
        email_template_name='users/auth/password_reset_email.html',
        subject_template_name='users/auth/password_reset_subject.txt'
    ), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='users/auth/password_reset_done.html'
    ), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', users_views.CustomPasswordResetConfirmView.as_view(
        template_name='users/auth/password_reset_confirm.html'
    ), name='password_reset_confirm'),
    path('password-reset-complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='users/auth/password_reset_complete.html'
    ), name='password_reset_complete'),

    # API
    path('api/v1/', include('analytics.urls')),
    path('api/v1/analytics/', include('conversion.urls')),

    # Public API Reference (no auth required)
    re_path(r'^api/v1/reference/schema(?P<format>\.json|\.yaml)$', public_schema_view.without_ui(cache_timeout=0), name='public-schema-json'),
    path('api/v1/reference/swagger/', public_schema_view.with_ui('swagger', cache_timeout=0), name='public-schema-swagger-ui'),
    path(
        'api/v1/reference/',
        TemplateView.as_view(
            template_name='redoc_branded.html',
            extra_context={'spec_url': '/api/v1/reference/schema.json'}
        ),
        name='public-schema-redoc'
    ),
]

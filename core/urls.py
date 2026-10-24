"""
URL configuration for Respectlytics Community Edition.

Clean URL config without website/tools/billing/demo apps.
"""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path
from django.views.generic import RedirectView, TemplateView
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

# Admin: always use SecureAdminSite (provides security dashboard).
# OTP (2FA) is only enforced when ADMIN_REQUIRE_OTP=True.
from analytics.admin_security import security_admin_site
from core.api_schema import KEYS_AND_ENDPOINTS, PublicEndpoints
from core.health import healthz
from users import secret_keys
from users import views as users_views
from users.views import (
    # DATA-001: Data management
    account_data_management_view,
    account_profile_view,
    account_security_view,
    # PROF-001: Account settings views
    account_view,
    # PROF-011: Account deletion
    delete_account_view,
    login_view,
    logout_view,
    register_view,
    registration_complete_view,
    resend_verification_email,
    verify_email,
)

# Copy all registered models from the default admin to our custom admin
for model_cls, model_admin in admin.site._registry.items():
    security_admin_site.register(model_cls, model_admin.__class__)

# API Documentation - Public (clean description, no internal references)
public_schema_view = get_schema_view(
    openapi.Info(
        title="Respectlytics API",
        default_version="v1",
        description=f"""Privacy-first mobile analytics API, Community Edition.

## Getting Started

1. [Create an account](/register/) and set up your first app
2. Copy your app key from the [Dashboard](/dashboard/)
3. Integrate with our SDKs or send events to the API directly

{KEYS_AND_ENDPOINTS.format(site="https://your-server")}
## SDKs

Official SDKs handle authentication, batching, and RAM-only event queue automatically:
- [Swift (iOS)](https://github.com/respectlytics/respectlytics-swift)
- [Kotlin (Android)](https://github.com/respectlytics/respectlytics-kotlin)
- [Flutter](https://github.com/respectlytics/respectlytics-flutter)
- [React Native](https://github.com/respectlytics/respectlytics-react-native)
""",
        license=openapi.License(name="AGPL-3.0"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
    generator_class=PublicEndpoints,
)

urlpatterns = [
    # Health check for Docker and uptime monitors: {"status": "ok"} and nothing else.
    path("healthz", healthz, name="healthz"),
    # Home: redirect to dashboard (login_required will redirect to login if needed)
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
    # SEC-009 & SEC-011: OTP-protected admin with security dashboard
    path("admin/", security_admin_site.urls),
    # Authentication
    path("register/", register_view, name="register"),
    path("register/complete/", registration_complete_view, name="registration_complete"),
    path("resend-verification/", resend_verification_email, name="resend_verification"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("verify-email/<uidb64>/<token>/", verify_email, name="verify_email"),
    # PROF-001: Account Settings (no billing, no preferences)
    path("account/", account_view, name="account"),
    path("account/profile/", account_profile_view, name="account_profile"),
    path("account/security/", account_security_view, name="account_security"),
    # DATA-001: Data management
    path("account/data-management/", account_data_management_view, name="account_data_management"),
    path("account/api-keys/", secret_keys.account_api_keys_view, name="account_api_keys"),
    path(
        "account/api-keys/<int:pk>/revoke/",
        secret_keys.account_api_key_revoke_view,
        name="account_api_key_revoke",
    ),
    # PROF-011: Account Deletion
    path("account/delete/", delete_account_view, name="account_delete"),
    # Dashboard (authenticated views)
    path("dashboard/", include("dashboard.urls")),
    # Password Reset (Django built-in with custom view for reply-to support)
    path(
        "password-reset/",
        users_views.CustomPasswordResetView.as_view(
            template_name="users/auth/password_reset.html",
            email_template_name="users/auth/password_reset_email.html",
            subject_template_name="users/auth/password_reset_subject.txt",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="users/auth/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset-confirm/<uidb64>/<token>/",
        users_views.CustomPasswordResetConfirmView.as_view(
            template_name="users/auth/password_reset_confirm.html"
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset-complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="users/auth/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    # API
    path("api/v1/", include("analytics.urls")),
    path("api/v1/analytics/", include("conversion.urls")),  # Conversion Intelligence endpoints
    # Public API Reference (no auth required)
    re_path(
        r"^api/v1/reference/schema\.(?P<format>json|yaml)$",
        public_schema_view.without_ui(cache_timeout=0),
        name="public-schema-json",
    ),
    path(
        "api/v1/reference/swagger/",
        public_schema_view.with_ui("swagger", cache_timeout=0),
        name="public-schema-swagger-ui",
    ),
    path(
        "api/v1/reference/",
        TemplateView.as_view(
            template_name="redoc_branded.html",
            extra_context={"spec_url": "/api/v1/reference/schema.json"},
        ),
        name="public-schema-redoc",
    ),
]

"""
SEC-011: Admin Security Dashboard Views — Community Edition

Custom admin site with security dashboard and action endpoints.
OTP (2FA) is conditional based on ADMIN_REQUIRE_OTP setting.
"""

import logging

from django.conf import settings
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path

from .security_dashboard import (
    get_banned_ips,
    get_locked_accounts,
    get_security_stats,
    lift_blocks,
    parse_security_log,
    unlock_account,
)

logger = logging.getLogger("analytics")

# Conditional OTP: use OTPAdminSite only if ADMIN_REQUIRE_OTP is True
if getattr(settings, "ADMIN_REQUIRE_OTP", False):
    from django_otp.admin import OTPAdminSite

    _BaseAdminSite = OTPAdminSite
else:
    _BaseAdminSite = admin.AdminSite


class SecurityAdminSite(_BaseAdminSite):
    """
    Custom admin site with security dashboard.

    OTP (2FA) is enabled only when ADMIN_REQUIRE_OTP=True in settings.

    Provides:
    - Security dashboard view with statistics
    - Banned IPs listing with unban action
    - Locked accounts listing with unlock action
    - Recent security events log viewer
    """

    site_header = "Respectlytics Admin"
    site_title = "Respectlytics Admin"
    index_title = "Administration"

    def get_urls(self):
        """Add custom security dashboard URLs."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "security/",
                self.admin_view(self.security_dashboard_view),
                name="security-dashboard",
            ),
            path(
                "security/unban-ip/", self.admin_view(self.unban_ip_view), name="security-unban-ip"
            ),
            path(
                "security/unlock-account/",
                self.admin_view(self.unlock_account_view),
                name="security-unlock-account",
            ),
        ]
        return custom_urls + urls

    def security_dashboard_view(self, request):
        """
        Security dashboard showing current security status.

        Displays:
        - 24-hour statistics (login failures, bans, etc.)
        - Currently banned IPs with unban action
        - Locked accounts with unlock action
        - Recent security events from log
        """
        context = {
            **self.each_context(request),
            "title": "Security Dashboard",
            "banned_ips": get_banned_ips(),
            "locked_accounts": get_locked_accounts(),
            "events": parse_security_log(limit=100, hours=24),
            "stats": get_security_stats(hours=24),
        }

        return TemplateResponse(request, "admin/security_dashboard.html", context)

    def unban_ip_view(self, request):
        """Lift a block: a row's Lift button sends its code, the form an address typed in."""
        if request.method == "POST":
            key, ip = request.POST.get("key", ""), request.POST.get("ip", "")
            deleted, reached = lift_blocks(key=key, ip=ip)
            if deleted:
                messages.success(request, "Lifted the block.")
                logger.info(f"[SECURITY] Admin {request.user.username} lifted a block")
            elif ip or key:
                messages.info(request, "There was no block to lift.")
            else:
                messages.error(request, "Type an IP address, or use a row's Lift button.")
            if not reached:
                messages.warning(
                    request,
                    "Cloudflare could not be reached, so it may still refuse this "
                    "address: remove it from the block list in the Cloudflare dashboard "
                    "(Manage Account, Configurations, Lists).",
                )

        return redirect("admin:security-dashboard")

    def unlock_account_view(self, request):
        """Handle account unlock action."""
        if request.method == "POST":
            email = request.POST.get("email")
            if email:
                if unlock_account(email):
                    messages.success(request, f"Successfully unlocked account: {email}")
                    logger.info(
                        f"[SECURITY] Admin {request.user.username} unlocked account: {email}"
                    )
                else:
                    messages.error(request, f"Failed to unlock account: {email}")
            else:
                messages.error(request, "No email address provided")

        return redirect("admin:security-dashboard")


# Create the custom admin site instance
security_admin_site = SecurityAdminSite(name="admin")

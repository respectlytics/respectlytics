"""
Enhanced User Admin — Community Edition

Stripped of billing/subscription inlines and columns.
Keeps lockout management (SEC-003) and preferences inline.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils.html import format_html
from django.contrib import messages
from .models import UserPreferences


# SEC-003: Lockout configuration (must match views.py)
LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATION = 1800  # 30 minutes in seconds


class UserPreferencesInline(admin.StackedInline):
    """Inline for email notification preferences."""
    model = UserPreferences
    can_delete = False
    verbose_name_plural = 'Email Preferences'
    fields = ['email_important_updates', 'email_product_news']


class CustomUserAdmin(BaseUserAdmin):
    """Enhanced User admin without subscription (Community Edition)."""
    inlines = [UserPreferencesInline]
    list_display = [
        'email', 'username', 'is_active', 'is_staff',
        'get_lockout_status', 'date_joined'
    ]
    list_filter = ['is_active', 'is_staff', 'is_superuser', 'date_joined']
    search_fields = ['email', 'username', 'first_name', 'last_name']
    actions = ['unlock_accounts']

    def get_lockout_status(self, obj):
        """
        SEC-003: Show account lockout status in list view.
        Checks cache for lockout and failed attempt data.
        """
        email_lower = obj.email.lower()
        is_locked = cache.get(f'account_locked:{email_lower}', False)
        failed_attempts = cache.get(f'login_failures:{email_lower}', 0)

        if is_locked:
            return format_html(
                '<span style="color: #dc2626; font-weight: bold;">🔒 LOCKED</span>'
            )
        elif failed_attempts > 0:
            color = '#f59e0b' if failed_attempts >= 3 else '#6b7280'
            return format_html(
                '<span style="color: {};">{}/{} attempts</span>',
                color, failed_attempts, LOCKOUT_THRESHOLD
            )
        return format_html('<span style="color: #10b981;">✓ OK</span>')
    get_lockout_status.short_description = 'Login Status'

    @admin.action(description='🔓 Unlock selected accounts (clear lockouts)')
    def unlock_accounts(self, request, queryset):
        """
        SEC-003: Admin action to unlock accounts.
        Clears lockout and failed attempt counters for selected users.
        """
        unlocked = 0
        already_unlocked = 0

        for user in queryset:
            email_lower = user.email.lower()
            is_locked = cache.get(f'account_locked:{email_lower}', False)
            failed_attempts = cache.get(f'login_failures:{email_lower}', 0)

            if is_locked or failed_attempts > 0:
                cache.delete(f'account_locked:{email_lower}')
                cache.delete(f'login_failures:{email_lower}')
                unlocked += 1
            else:
                already_unlocked += 1

        if unlocked > 0:
            self.message_user(
                request,
                f'Successfully unlocked {unlocked} account(s).',
                messages.SUCCESS
            )
        if already_unlocked > 0:
            self.message_user(
                request,
                f'{already_unlocked} account(s) were already unlocked.',
                messages.INFO
            )


# Unregister default User admin and register our custom one
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(UserPreferences)
class UserPreferencesAdmin(admin.ModelAdmin):
    """Standalone admin for UserPreferences (also available as inline on User)."""
    list_display = ['user_email', 'email_important_updates', 'email_product_news', 'updated_at']
    list_filter = ['email_important_updates', 'email_product_news']
    search_fields = ['user__email', 'user__username']
    readonly_fields = ['created_at', 'updated_at']

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'Email'
    user_email.admin_order_field = 'user__email'

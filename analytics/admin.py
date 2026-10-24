import ipaddress

from django.contrib import admin, messages
from django.utils import timezone

from .blocks import address_key, lift
from .models import App, BlockedAddress, Event, SecretKey


@admin.register(App)
class AppAdmin(admin.ModelAdmin):
    list_display = ["name", "id", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["name", "id"]
    readonly_fields = ["id", "created_at"]


@admin.register(SecretKey)
class SecretKeyAdmin(admin.ModelAdmin):
    """An account's API secret keys: who has one and when it was used. A key itself is never
    stored, so nothing here can show it; deleting a row revokes that key."""

    list_display = ["start", "user", "created_at", "last_used_at"]
    search_fields = ["user__email", "start"]
    readonly_fields = ["user", "start", "created_at", "last_used_at"]
    exclude = ["digest"]

    def has_add_permission(self, request):
        return False  # made by their owner on the account page, shown to them once


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["event_name", "app", "timestamp", "country", "platform"]
    list_filter = ["event_name", "timestamp", "country", "platform"]
    search_fields = ["event_name", "app__name", "session_id"]
    readonly_fields = ["id", "timestamp"]
    date_hierarchy = "timestamp"


@admin.register(BlockedAddress)
class BlockedAddressAdmin(admin.ModelAdmin):
    """The blocks in analytics/blocks.py. A block keeps only a code computed from the address,
    so a search for an address computes that code."""

    list_display = ["code", "kind", "reason", "times", "last_blocked", "expires_at", "is_active"]
    list_filter = ["kind"]
    search_fields = ["reason"]
    search_help_text = "Type an IP address to find its block, or words from the reason."
    readonly_fields = [
        "key",
        "kind",
        "reason",
        "times",
        "first_blocked",
        "last_blocked",
        "expires_at",
    ]
    actions = ["lift_blocks"]

    def has_add_permission(self, request):
        return False

    @admin.display(description="code")
    def code(self, obj):
        return obj.key[:12]

    @admin.display(boolean=True, description="active")
    def is_active(self, obj):
        return obj.expires_at > timezone.now()

    def get_search_results(self, request, queryset, search_term):
        try:
            ip = str(ipaddress.ip_address(search_term.strip()))
        except ValueError:
            return super().get_search_results(request, queryset, search_term)
        return queryset.filter(key=address_key(ip)), False

    @admin.action(description="Lift the selected blocks")
    def lift_blocks(self, request, queryset):
        count, reached = lift(queryset.values_list("key", flat=True))
        self.message_user(
            request, f"Lifted {count} block{'s' if count != 1 else ''}.", messages.SUCCESS
        )
        if not reached:
            self.message_user(
                request,
                "Cloudflare could not be reached, so it may still refuse these addresses: remove "
                "them from the block list in the Cloudflare dashboard (Manage Account, "
                "Configurations, Lists).",
                messages.WARNING,
            )

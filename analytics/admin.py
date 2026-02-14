from django.contrib import admin
from .models import App, Event


@admin.register(App)
class AppAdmin(admin.ModelAdmin):
    list_display = ['name', 'id', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'id']
    readonly_fields = ['id', 'created_at']


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['event_name', 'app', 'timestamp', 'country', 'platform']
    list_filter = ['event_name', 'timestamp', 'country', 'platform']
    search_fields = ['event_name', 'app__name', 'session_id']
    readonly_fields = ['id', 'timestamp']
    date_hierarchy = 'timestamp'

"""
URL patterns for authenticated dashboard views.

All views here require login and display analytics UI.
Separated from website/ (public pages) and analytics/ (API endpoints).
"""
from django.urls import path
from .views import (
    dashboard_view, stats_view, funnel_view, save_conversion_preferences,
    update_app_name, delete_app, get_app_event_count,
    dashboard_delete_events_preview, dashboard_delete_events,
)

app_name = 'dashboard'

urlpatterns = [
    # Main dashboard
    path('', dashboard_view, name='main'),
    
    # Per-app analytics views
    path('stats/<slug:app_slug>/', stats_view, name='stats'),
    path('funnel/<slug:app_slug>/', funnel_view, name='funnel'),
    
    # Conversion preferences API (TASK-040)
    path('api/preferences/<slug:app_slug>/conversion-events/', 
         save_conversion_preferences, name='save_conversion_preferences'),
    
    # App management API
    path('api/apps/<slug:app_slug>/update/', update_app_name, name='update_app_name'),
    path('api/apps/<slug:app_slug>/delete/', delete_app, name='delete_app'),
    path('api/apps/<slug:app_slug>/event-count/', get_app_event_count, name='get_app_event_count'),
    
    # Event data deletion (dashboard)
    path('api/apps/<slug:app_slug>/events/delete/preview/', dashboard_delete_events_preview, name='delete_events_preview'),
    path('api/apps/<slug:app_slug>/events/delete/', dashboard_delete_events, name='delete_events'),
]

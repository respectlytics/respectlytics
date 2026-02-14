from django.urls import path
from .views import (
    api_root, health_check, AppListCreateView, AppRegenerateKeyView, EventCreateView, EventSummaryView, EventCountView, GeoSummaryView,
    FunnelAnalysisView, EventTypesView, FilterOptionsView, ExportEventsView, RecentActivityView,
    list_all_apps, DeleteEventsPreviewView, DeleteEventsView, DeletionHistoryView
)

app_name = 'analytics'

urlpatterns = [
    # Health check (for load balancers - no auth, excluded from docs)
    path('health/', health_check, name='health-check'),
    
    # API endpoints
    path('', api_root, name='api-root'),
    path('apps/', AppListCreateView.as_view(), name='app-list-create'),
    path('apps/<slug:app_slug>/regenerate-key/', AppRegenerateKeyView.as_view(), name='app-regenerate-key'),
    path('apps/list-all/', list_all_apps, name='apps-list-all'),
    path('events/', EventCreateView.as_view(), name='event-create'),
    path('events/summary/', EventSummaryView.as_view(), name='event-summary'),
    path('events/count/', EventCountView.as_view(), name='event-count'),
    path('events/geo-summary/', GeoSummaryView.as_view(), name='geo-summary'),
    path('events/funnel/', FunnelAnalysisView.as_view(), name='event-funnel'),
    path('events/event-types/', EventTypesView.as_view(), name='event-types'),
    path('events/filter-options/', FilterOptionsView.as_view(), name='filter-options'),
    path('events/export/', ExportEventsView.as_view(), name='event-export'),
    path('events/recent-activity/', RecentActivityView.as_view(), name='recent-activity'),
    
    # Event data deletion endpoints
    path('events/delete/preview/', DeleteEventsPreviewView.as_view(), name='event-delete-preview'),
    path('events/delete/', DeleteEventsView.as_view(), name='event-delete'),
    path('events/deletions/', DeletionHistoryView.as_view(), name='deletion-history'),
    
    # NOTE: Conversion Intelligence endpoints moved to conversion/ app
    # See: conversion/urls.py for DAU, Conversions, TimeToConversion, StepTiming
    
    # NOTE: Web UI views (home, docs, stats, funnel, privacy, terms) moved to website/ app
    # See: website/urls.py
]

"""
Conversion Intelligence URLs

These endpoints provide advanced analytics for understanding session conversion patterns:
- DAU/WAU/MAU (Active Sessions)
- Conversion counts and rates
- Time-to-conversion analysis
- Funnel step timing analysis
- Auto-generated conversion paths
- Drop-off diagnostics
- Event correlation (Conversion Drivers)
- Segment comparison (Platform, Country)

All analytics are session-based (no cross-session tracking by design).
"""
from django.urls import path
from .views import (
    DAUView, 
    ConversionSummaryView, 
    TimeToConversionView, 
    StepTimingView,
    ConversionPathsView,
    DropOffView,
    EventCorrelationView,
    SegmentComparisonView,
    GlobeStatsView,
)

app_name = 'conversion'

urlpatterns = [
    # Conversion Intelligence endpoints - Session-Based Analytics
    path('dau/', DAUView.as_view(), name='dau'),
    path('conversions/', ConversionSummaryView.as_view(), name='conversions'),
    path('time-to-conversion/', TimeToConversionView.as_view(), name='time-to-conversion'),
    path('step-timing/', StepTimingView.as_view(), name='step-timing'),
    path('conversion-paths/', ConversionPathsView.as_view(), name='conversion-paths'),
    path('drop-off/', DropOffView.as_view(), name='drop-off'),
    path('event-correlation/', EventCorrelationView.as_view(), name='event-correlation'),
    path('segments/', SegmentComparisonView.as_view(), name='segments'),
    path('globe-stats/', GlobeStatsView.as_view(), name='globe-stats'),
]

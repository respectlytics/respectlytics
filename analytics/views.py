"""
Analytics API Views — Community Edition

This module contains all API views for the analytics application.
Organized into sections:
1. Base/Utility Views (health_check, api_root)
2. App Management Views (AppListCreateView, AppRegenerateKeyView)
3. Event Views (EventCreateView, EventSummaryView)
4. Analytics Views (GeoSummaryView, FunnelAnalysisView, EventTypesView, FilterOptionsView)
5. Export/Activity Views (ExportEventsView, RecentActivityView)

Community Edition differences:
- EventCreateView.post() has no billing/quota checks (unlimited events) and keeps no declared
  properties
- AppListCreateView creates apps without a plan's limit
- api_root() references /api/v1/reference/ only (no staff-only swagger/redoc)
"""

import csv
import json
import logging
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db.models import Count
from django.http import HttpResponse, StreamingHttpResponse
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import event_groups
from .authentication import APP_OWNER, AppKeyAuthentication
from .base_events import base_events, session_count, slices_in
from .client_ip import get_client_ip
from .date_utils import (
    freshness_mark,
    get_cache_key_with_timezone,
    parse_date_range,
)
from .event_groups import known_names, with_groups
from .filter_values import countries_and_platforms
from .geolocation import get_location_from_ip
from .intake import country_code, platform_name
from .models import App, DeletionLog, Event
from .permissions import HasValidAppKey, IsAppOwner
from .security_logger import SecurityEvent, log_security_event
from .serializers import AppSerializer, EventCreateSerializer
from .summary import summary_figures

logger = logging.getLogger(__name__)


# =============================================================================
# SECTION 1: BASE/UTILITY VIEWS
# =============================================================================


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health_check(request):
    """
    Health check endpoint for load balancers and monitoring.
    Returns 200 if the service is healthy.

    Checks:
    - Django can process requests
    - Database is accessible (SELECT 1)
    """
    from django.db import connection
    from django.utils import timezone

    health_status = {"status": "healthy", "timestamp": timezone.now().isoformat(), "checks": {}}

    # Check database connectivity
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        health_status["checks"]["database"] = "ok"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = f"error: {str(e)}"
        return Response(health_status, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    return Response(health_status, status=status.HTTP_200_OK)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def api_root(request):
    """
    Respectlytics API Root — Community Edition

    Welcome to the Respectlytics API - a privacy-first mobile analytics platform.

    > ⚠️ **AUTHENTICATION REQUIRED:** All endpoints require app_key authentication.

    **Mobile App API Endpoints:**
    - POST /api/v1/events/ - Submit an analytics event
    - GET /api/v1/events/summary/ - Get aggregated analytics data
    - GET /api/v1/events/geo-summary/ - Get geographic distribution
    - GET /api/v1/events/funnel/ - Analyze conversion funnels
    - GET /api/v1/events/event-types/ - List all event types for your app

    **Getting Started:**
    1. Register at /register/ and login at /login/
    2. Create an app via the Dashboard at /dashboard/
    3. Copy your app_key and use it in your mobile app
    4. Send events from your app using the X-App-Key header

    Documentation:
    - API Reference: /api/v1/reference/
    """
    return Response(
        {
            "message": "Welcome to Respectlytics API, Community Edition",
            "version": "1.0",
            "edition": "community",
            "endpoints": {
                "events": {
                    "create": "/api/v1/events/",
                    "summary": "/api/v1/events/summary/",
                    "geo_summary": "/api/v1/events/geo-summary/",
                    "funnel": "/api/v1/events/funnel/",
                    "event_types": "/api/v1/events/event-types/",
                    "methods": {
                        "create": ["POST"],
                        "summary": ["GET"],
                        "geo_summary": ["GET"],
                        "funnel": ["GET"],
                        "event_types": ["GET"],
                    },
                }
            },
            "documentation": {
                "reference": "/api/v1/reference/",
            },
            "authentication": {
                "type": "App Key (UUID)",
                "header": "X-App-Key",
                "info": "Provide your app_key via X-App-Key header, query param, or request body",
                "example_header": "X-App-Key: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                "get_key": "Create an app at /dashboard/ to receive your API key",
            },
        }
    )


# =============================================================================
# SECTION 2: APP MANAGEMENT VIEWS
# =============================================================================


class AppListCreateView(generics.ListCreateAPIView):
    """
    Internal endpoint for web dashboard app management.
    Not included in public API documentation.

    GET /api/apps/ - List user's apps (requires user authentication)
    POST /api/apps/ - Create a new app (requires user authentication)

    Authentication: Must be logged in as a user via Django session
    """

    serializer_class = AppSerializer
    authentication_classes = [SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    # Exclude from public API documentation (Swagger/ReDoc)
    swagger_schema = None

    def get_queryset(self):
        """Return only apps belonging to the authenticated user"""
        # request.user should be a User object when using session auth
        # Check if user exists and has is_authenticated attribute
        user = getattr(self.request, "user", None)
        if user and hasattr(user, "is_authenticated") and user.is_authenticated:
            return App.objects.filter(user=user)
        return App.objects.none()

    def perform_create(self, serializer):
        """Automatically set the user when creating an app"""
        serializer.save(user=self.request.user)


class AppRegenerateKeyView(APIView):
    """
    Regenerate the API key for an app.
    Requires session authentication and ownership verification.
    Internal endpoint - not included in public API documentation.
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    # Exclude from public API documentation
    swagger_schema = None

    def post(self, request, app_slug):
        try:
            app = App.objects.get(slug=app_slug, user=request.user)
        except App.DoesNotExist:
            return Response({"error": "App not found"}, status=status.HTTP_404_NOT_FOUND)

        # Store app name for logging before regeneration
        app_name = app.name

        # Regenerate the key (this will modify the app object)
        old_app_key, new_app_key = app.regenerate_key()

        # Log the action
        logger.info(
            f"API key regenerated for app '{app_name}' (slug: {app_slug}) "
            f"by user {request.user.username}"
        )

        return Response(
            {
                "success": True,
                "new_app_key": str(new_app_key),
                "message": "API key regenerated successfully. The old key is now invalid.",
                "warning": (
                    "Make sure to update your mobile app configuration with the new key. Apps "
                    "using the old key will stop working immediately."
                ),
            },
            status=status.HTTP_200_OK,
        )


# =============================================================================
# SECTION 3: CORE EVENT VIEWS
# =============================================================================


class EventCreateView(APIView):
    """
    POST /api/v1/events/ - Create a new event (requires authentication)

    Community Edition: No billing/quota checks. Unlimited events.
    """

    authentication_classes = [AppKeyAuthentication]
    permission_classes = [HasValidAppKey]

    @swagger_auto_schema(
        operation_description="""Submit an analytics event from your mobile app.

**Privacy-First Validation:**
Respectlytics enforces strict server-side privacy guards. Your request must:
- Only include fields from the allowed list (see request body schema)
- Use properly formatted session_id (16+ random chars, NOT UUID format)

**Stored Fields:** Only these fields are persisted:
event_name, session_id, timestamp, platform, country.

**Deprecated Fields (accepted but ignored):** For backwards compatibility, these fields are
still accepted but are NOT stored: device_type, os_version, app_version, locale, region,
screen. Update your SDK to stop sending these fields.

**Geolocation:** If you don't provide `country`, it will be automatically detected from your
IP address. IP addresses are NEVER stored: they are used only for the lookup and immediately
discarded.

**Session Anonymization:** Session IDs are hashed with a daily-rotating salt before storage.
This prevents cross-session tracking while enabling same-day funnel analysis.""",
        manual_parameters=[
            openapi.Parameter(
                "X-App-Key",
                openapi.IN_HEADER,
                description="Your app's API key (UUID)",
                type=openapi.TYPE_STRING,
                required=True,
            ),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["event_name"],
            properties={
                "event_name": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Event name (e.g., "app_open", "purchase")',
                ),
                "session_id": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description=(
                        "Session identifier - must be 16+ random chars, NOT a UUID format. "
                        "Anonymized with daily rotation."
                    ),
                ),
                "timestamp": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="ISO 8601 timestamp - auto-set to current time if omitted",
                ),
                "platform": openapi.Schema(
                    type=openapi.TYPE_STRING, description="Platform: ios, android, web, or other"
                ),
                "country": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Country code (e.g., "US") - auto-detected if omitted',
                ),
                # Deprecated fields - accepted for backwards compatibility but not stored
                "region": openapi.Schema(
                    type=openapi.TYPE_STRING, description="DEPRECATED: Accepted but not stored"
                ),
                "device_type": openapi.Schema(
                    type=openapi.TYPE_STRING, description="DEPRECATED: Accepted but not stored"
                ),
                "os_version": openapi.Schema(
                    type=openapi.TYPE_STRING, description="DEPRECATED: Accepted but not stored"
                ),
                "app_version": openapi.Schema(
                    type=openapi.TYPE_STRING, description="DEPRECATED: Accepted but not stored"
                ),
                "locale": openapi.Schema(
                    type=openapi.TYPE_STRING, description="DEPRECATED: Accepted but not stored"
                ),
                "screen": openapi.Schema(
                    type=openapi.TYPE_STRING, description="DEPRECATED: Accepted but not stored"
                ),
            },
        ),
        responses={
            201: openapi.Response(
                description="Event created successfully",
                examples={
                    "application/json": {
                        "id": 12345,
                        "event_name": "purchase",
                        "timestamp": "2025-11-12T10:30:00Z",
                        "message": "Event created successfully",
                    }
                },
            ),
            400: openapi.Response(
                description="Bad Request - Privacy violation or invalid data",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "detail": openapi.Schema(
                            type=openapi.TYPE_STRING, description="Error summary"
                        ),
                        "code": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description=(
                                "Error code: FORBIDDEN_FIELD, FORBIDDEN_FIELDS, or "
                                "INVALID_SESSION_ID"
                            ),
                            enum=["FORBIDDEN_FIELD", "FORBIDDEN_FIELDS", "INVALID_SESSION_ID"],
                        ),
                        "reason": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Detailed explanation with fix instructions",
                        ),
                    },
                ),
                examples={
                    "application/json": {
                        "FORBIDDEN_FIELD": {
                            "detail": "Invalid request",
                            "code": "FORBIDDEN_FIELD",
                            "reason": (
                                "Field 'device_id' is not allowed. Respectlytics only accepts: "
                                "app_key, app_version, country, device_type, event_name, locale, "
                                "os_version, platform, region, screen, session_id, timestamp."
                            ),
                        },
                        "INVALID_SESSION_ID": {
                            "detail": "Invalid request",
                            "code": "INVALID_SESSION_ID",
                            "reason": (
                                "session_id appears to be a device identifier or predictable "
                                "pattern. Use a random string generated fresh for each app "
                                "session."
                            ),
                        },
                    }
                },
            ),
            401: openapi.Response(
                description="Unauthorized - missing or invalid app_key",
                examples={
                    "application/json": {"detail": "Authentication credentials were not provided."}
                },
            ),
        },
    )
    def post(self, request):
        # One event per request, as a JSON object: an array (how the Kotlin SDK before 3.1.0
        # sent its queue), a string or a number is refused with what to send, never a 500
        if not isinstance(request.data, dict):
            return Response(
                {
                    "detail": "Send one event per request, as a JSON object.",
                    "code": "not_an_object",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Get the authenticated app
        app = request.user

        # Create event data with the authenticated app
        event_data = request.data.copy()
        event_data["app_key"] = str(app.id)

        # Auto-detect country from IP if not provided
        # User-provided values always take precedence
        # NOTE: Region is no longer auto-populated (schema reduction for privacy compliance)
        # A country that is not an ISO code counts as none (analytics/intake.py)
        if not country_code(event_data.get("country")):
            event_data["country"] = None
            client_ip = get_client_ip(request)
            detected_country, _ = get_location_from_ip(client_ip)

            # Log for debugging geolocation issues (no IP logged — privacy by design)
            if not detected_country:
                logger.info("Geolocation failed: no country detected for incoming request")
            else:
                logger.debug(f"Geolocation success: detected {detected_country}")

            # Use detected country only if user didn't provide it
            if detected_country:
                event_data["country"] = detected_country

        # Pass request context for session processing
        # The serializer uses request.META for additional context if needed
        serializer = EventCreateSerializer(data=event_data, context={"request": request})
        if serializer.is_valid():
            event = serializer.save()

            return Response(
                {
                    "id": event.id,
                    "event_name": event.event_name,
                    "timestamp": event.timestamp,
                    "message": "Event created successfully",
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EventSummaryView(APIView):
    """
    GET /api/v1/events/summary/ - Get aggregated event data (requires authentication)
    Query parameters:
        - from: Start date (YYYY-MM-DD)
        - to: End date (YYYY-MM-DD)

    Returns data for the authenticated app, with `event_groups`: events of one kind counted
    together and split (analytics/event_groups.py).
    """

    share_links = True  # a share link's dashboard reads it (teams/)
    authentication_classes = APP_OWNER
    permission_classes = [HasValidAppKey]

    def get(self, request):
        # Get the authenticated app
        app = request.user
        from_date = request.query_params.get("from")
        to_date = request.query_params.get("to")
        tz_name = request.query_params.get("tz", "UTC")

        # PERF-006: Cache summary data for 1 minute
        # Summary data updates frequently but is expensive to compute
        from django.conf import settings
        from django.core.cache import cache

        cache_key = get_cache_key_with_timezone(
            "summary",
            app.id,
            from_date,
            to_date,
            tz_name,
            fresh=freshness_mark(app.id, to_date, getattr(settings, "CACHE_TTL_SUMMARY", 60)),
        )
        cached_result = cache.get(cache_key)

        if cached_result is not None:
            return Response(with_groups(cached_result, app))

        # Start with events for this app
        events = Event.objects.filter(app=app)

        # Apply date filters if provided (timezone-aware)
        try:
            from_datetime, to_datetime = parse_date_range(from_date, to_date, tz_name)
            if from_datetime:
                events = events.filter(timestamp__gte=from_datetime)
            if to_datetime:
                events = events.filter(timestamp__lte=to_datetime)
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Two passes over the range (analytics/summary.py)
        slices = slices_in(app, from_datetime, to_datetime)
        response_data = {"app_name": app.name, **summary_figures(events, slices, tz_name)}

        # Cache the result for 1 minute
        cache_ttl = getattr(settings, "CACHE_TTL_SUMMARY", 60)
        cache.set(cache_key, response_data, timeout=cache_ttl)

        return Response(with_groups(response_data, app))


class EventCountView(APIView):
    """
    GET /api/v1/events/count/ - Get fast event count for processing status
    Query parameters:
        - from: Start date (YYYY-MM-DD)
        - to: End date (YYYY-MM-DD)

    Returns only the count without expensive aggregations.
    Optimized for showing processing banners with accurate event counts.
    """

    share_links = True  # a share link's dashboard reads it (teams/)
    authentication_classes = APP_OWNER
    permission_classes = [HasValidAppKey]

    def get(self, request):
        app = request.user
        from_date = request.query_params.get("from")
        to_date = request.query_params.get("to")
        tz_name = request.query_params.get("tz", "UTC")

        # PERF-022: Cache event count for 1 minute
        from django.core.cache import cache

        cache_key = get_cache_key_with_timezone("event_count", app.id, from_date, to_date, tz_name)
        cached_result = cache.get(cache_key)

        if cached_result is not None:
            return Response(cached_result)

        # Start with events for this app
        events = Event.objects.filter(app=app)

        # Apply date filters if provided (timezone-aware)
        try:
            from_datetime, to_datetime = parse_date_range(from_date, to_date, tz_name)
            if from_datetime:
                events = events.filter(timestamp__gte=from_datetime)
            if to_datetime:
                events = events.filter(timestamp__lte=to_datetime)
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Single fast COUNT(*) query
        total_events = events.count()

        response_data = {
            "total_events": total_events,
            "date_range": {"from": from_date, "to": to_date},
        }

        # Cache for 1 minute
        cache.set(cache_key, response_data, timeout=60)

        return Response(response_data)


# =============================================================================
# SECTION 4: ANALYTICS VIEWS
# =============================================================================


class GeoSummaryView(APIView):
    """
    GET /api/v1/events/geo-summary/ - Get geographic distribution of events

    Query parameters:
        - from: Start date (YYYY-MM-DD)
        - to: End date (YYYY-MM-DD)
        - limit: Number of results per category (default: 20)

    Returns aggregated data by country for map visualizations.
    """

    share_links = True  # a share link's dashboard reads it (teams/)
    authentication_classes = APP_OWNER
    permission_classes = [HasValidAppKey]

    @swagger_auto_schema(
        operation_description="Get geographic distribution of events for map visualizations",
        manual_parameters=[
            openapi.Parameter(
                "X-App-Key",
                openapi.IN_HEADER,
                description="App Key for authentication",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "from",
                openapi.IN_QUERY,
                description="Start date in YYYY-MM-DD format",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "to",
                openapi.IN_QUERY,
                description="End date in YYYY-MM-DD format",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "tz",
                openapi.IN_QUERY,
                description=(
                    "IANA timezone name (e.g., 'America/New_York', 'Europe/London'). Dates are "
                    "interpreted in this timezone. Defaults to UTC."
                ),
                type=openapi.TYPE_STRING,
                required=False,
                default="UTC",
            ),
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="Maximum results per category (default: 20)",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Geographic distribution data",
                examples={
                    "application/json": {
                        "app_name": "My Mobile App",
                        "app_key": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                        "total_events": 15420,
                        "countries": [
                            {"country": "US", "count": 8500, "percentage": 55.1},
                            {"country": "CA", "count": 3200, "percentage": 20.8},
                            {"country": "UK", "count": 2100, "percentage": 13.6},
                        ],
                    }
                },
            ),
            400: "Bad Request - invalid date format",
            401: "Unauthorized - missing or invalid app_key",
        },
    )
    def get(self, request):
        # Get the authenticated app
        app = request.user

        # Parse query parameters
        from_date = request.query_params.get("from")
        to_date = request.query_params.get("to")
        tz_name = request.query_params.get("tz", "UTC")
        try:
            limit = min(max(int(request.query_params.get("limit", 20)), 1), 250)
        except (TypeError, ValueError):
            return Response({"error": "limit must be a whole number."}, status=400)

        # Start with events for this app
        events = Event.objects.filter(app=app)

        # Apply date filters if provided (timezone-aware)
        try:
            from_datetime, to_datetime = parse_date_range(from_date, to_date, tz_name)
            if from_datetime:
                events = events.filter(timestamp__gte=from_datetime)
            if to_datetime:
                events = events.filter(timestamp__lte=to_datetime)
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST
            )

        total_events = events.count()

        # Countries with counts and percentages
        countries_data = list(
            events.filter(country__isnull=False)
            .exclude(country="")
            .values("country")
            .annotate(count=Count("id"))
            .order_by("-count")[:limit]
        )

        # Add percentage to countries
        for item in countries_data:
            item["percentage"] = (
                round((item["count"] / total_events * 100), 1) if total_events > 0 else 0
            )

        return Response(
            {
                "app_name": app.name,
                "total_events": total_events,
                "countries": countries_data,
            }
        )


class FunnelAnalysisView(APIView):
    """
    GET /api/v1/events/funnel/ - Analyze conversion funnel through sequential steps

    Query parameters:
        - steps: Comma-separated event names in order (e.g., "app_open,product_view,purchase")
        - from: Start date (YYYY-MM-DD)
        - to: End date (YYYY-MM-DD)

    Returns step-by-step counts based on session progression.
    A session reaches step N only if it completed step N-1 earlier in time.
    """

    share_links = True  # a share link's dashboard reads it (teams/)
    authentication_classes = APP_OWNER
    permission_classes = [HasValidAppKey]

    @swagger_auto_schema(
        operation_description="Analyze conversion funnel through sequential event steps",
        manual_parameters=[
            openapi.Parameter(
                "X-App-Key",
                openapi.IN_HEADER,
                description="App Key for authentication",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "steps",
                openapi.IN_QUERY,
                description=(
                    "Comma-separated event names in order (e.g., 'app_open,product_view,purchase')"
                ),
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "from",
                openapi.IN_QUERY,
                description="Start date in YYYY-MM-DD format",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "to",
                openapi.IN_QUERY,
                description="End date in YYYY-MM-DD format",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "tz",
                openapi.IN_QUERY,
                description=(
                    "IANA timezone name (e.g., 'America/New_York', 'Europe/London'). Dates are "
                    "interpreted in this timezone. Defaults to UTC."
                ),
                type=openapi.TYPE_STRING,
                required=False,
                default="UTC",
            ),
            openapi.Parameter(
                "country",
                openapi.IN_QUERY,
                description="Filter by country code (e.g., 'US')",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "platform",
                openapi.IN_QUERY,
                description="Filter by platform (ios, android, web, other)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "window_minutes",
                openapi.IN_QUERY,
                description=(
                    "Step timeout in minutes - max time allowed between consecutive funnel steps "
                    "(e.g., '30' for 30 minutes). Sessions are max 2 hours, so values above 120 "
                    "have no effect. If not specified, no time limit is applied."
                ),
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Funnel analysis results",
                examples={
                    "application/json": {
                        "app_name": "My Mobile App",
                        "app_key": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                        "funnel": [
                            {"step": "app_open", "count": 1000},
                            {"step": "product_view", "count": 420},
                            {"step": "purchase", "count": 90},
                        ],
                        "total_sessions_analyzed": 1200,
                    }
                },
            ),
            400: "Bad request - missing or invalid parameters",
            401: "Unauthorized - missing or invalid app_key",
        },
    )
    def get(self, request):
        """
        PERF-003: Optimized funnel analysis using PostgreSQL.

        Instead of loading all events into Python memory, we use SQL to:
        1. Get only the relevant events for funnel steps
        2. Use window functions to track step progression per session
        3. Count sessions reaching each step directly in the database

        This reduces memory usage from O(events) to O(steps) and query time
        from O(n) Python iteration to O(1) SQL aggregation.
        """
        from django.db import connection

        # Get the authenticated app
        app = request.user

        # Parse steps parameter (required)
        steps_param = request.query_params.get("steps")
        if not steps_param:
            return Response(
                {"error": "Missing required parameter: steps (comma-separated event names)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        steps = [step.strip() for step in steps_param.split(",") if step.strip()]
        if len(steps) < 2:
            return Response(
                {"error": "At least 2 steps are required for funnel analysis"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(steps) > 10:
            return Response(
                {"error": "Maximum 10 steps allowed for funnel analysis"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get date filters
        from_date = request.query_params.get("from")
        to_date = request.query_params.get("to")
        tz_name = request.query_params.get("tz", "UTC")

        # Get additional filters (support multiple values comma-separated)
        # Note: region, device_type, os_version, app_version, locale, screen removed
        # (schema reduction)
        country = request.query_params.get("country")
        platform = request.query_params.get("platform")

        # Get step timeout (in minutes) - max time between consecutive steps
        # Sessions are max 2 hours, so this controls how strict the funnel timing is
        window_minutes = request.query_params.get("window_minutes")
        window_seconds = None
        if window_minutes:
            try:
                window_seconds = int(window_minutes) * 60  # Convert minutes to seconds
            except ValueError:
                return Response(
                    {"error": "Invalid window_minutes value. Must be a positive integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # PERF-006: Check cache before running expensive funnel analysis
        import hashlib

        from django.conf import settings
        from django.core.cache import cache

        # Cache key only includes stored fields (schema reduction)
        # A step may be a group's name (`group_events=true`), standing for any of its events
        grouping = event_groups.from_request(request, app)
        step_names = [grouping.expand([step]) for step in steps]
        cache_params = (
            f"{steps_param}:{from_date}:{to_date}:{tz_name}:{country}:{platform}:{window_minutes}"
            f":{grouping.key()}"
        )
        cache_hash = hashlib.md5(cache_params.encode()).hexdigest()[:16]
        cache_key = f"funnel:{app.id}:{cache_hash}"

        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return Response(cached_result)

        # Build base queryset with filters
        events = Event.objects.filter(app=app)

        # Apply filters with support for multiple values
        # Note: Only country and platform remain after schema reduction
        if country:
            country_list = [c.strip() for c in country.split(",") if c.strip()]
            if country_list:
                events = events.filter(country__in=country_list)

        if platform:
            # As sent and as intake names it, so "ios" finds "iOS" (analytics/intake.py)
            asked = [p.strip() for p in platform.split(",") if p.strip()]
            platform_list = sorted(set(asked) | {platform_name(p) for p in asked})
            if platform_list:
                events = events.filter(platform__in=platform_list)

        # Apply date filters (timezone-aware)
        try:
            from_datetime, to_datetime = parse_date_range(from_date, to_date, tz_name)
            if from_datetime:
                events = events.filter(timestamp__gte=from_datetime)
            if to_datetime:
                events = events.filter(timestamp__lte=to_datetime)
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Only consider events that match the funnel steps
        events = events.filter(event_name__in=[name for names in step_names for name in names])

        # Only consider sessions that have a session_id
        events = events.exclude(session_id__isnull=True).exclude(session_id="")

        # Get the SQL and params from the Django queryset
        # We'll use this as a subquery for our funnel analysis
        base_sql, base_params = base_events(events)

        # Each session's first moment at each step, in one pass over the steps' events (the
        # funnel only ever reads a step's first occurrence in a session), then how far the
        # session got: step i+1 counts when its first moment comes after step i's, and within
        # the window when one is set. Until 2026-10-26 a recursive query walked the same first
        # occurrences; analytics/test_funnel.py holds this to it. A name in two steps belongs to
        # the first, as before.
        num_steps = len(steps)
        owner = {}
        for i, names in enumerate(step_names):
            for name in names:
                owner.setdefault(name, i)
        firsts, first_params = [], []
        for i in range(num_steps):
            names = [name for name, step in owner.items() if step == i]
            if names:
                placeholders = ", ".join(["%s"] * len(names))
                firsts.append(
                    f"MIN(timestamp) FILTER (WHERE event_name IN ({placeholders})) AS t{i}"
                )
                first_params += names
            else:
                firsts.append(f"NULL::timestamptz AS t{i}")

        def follows(i):
            condition = f"t{i} > t{i - 1}"
            if window_seconds:
                condition += f" AND EXTRACT(EPOCH FROM (t{i} - t{i - 1})) <= %s"
            return f"COALESCE({condition}, false)"

        reached = " ".join(f"WHEN NOT {follows(i)} THEN {i - 1}" for i in range(1, num_steps))
        funnel_sql = f"""
        WITH base_events AS ({base_sql}),
        firsts AS (
            SELECT {", ".join(firsts)}
            FROM base_events
            GROUP BY session_id COLLATE "C"
        ),
        reached AS (
            SELECT CASE WHEN t0 IS NULL THEN -1 {reached} ELSE {num_steps - 1} END AS max_step
            FROM firsts
        )
        SELECT s.step_index, COUNT(*)
        FROM reached CROSS JOIN LATERAL generate_series(0, reached.max_step) AS s(step_index)
        GROUP BY s.step_index
        ORDER BY s.step_index
        """
        params = [*base_params, *first_params]
        if window_seconds:
            params += [window_seconds] * (num_steps - 1)

        with connection.cursor() as cursor:
            cursor.execute(funnel_sql, params)
            rows = cursor.fetchall()

        # Convert results to step counts dict
        step_counts = {i: 0 for i in range(len(steps))}
        for row in rows:
            step_index, count = row
            if step_index is not None and step_index in step_counts:
                step_counts[step_index] = count

        # Get total sessions analyzed (sessions that have at least one funnel event)
        # The sessions with any step's event, from the same filters' session slices: one row or
        # two per session instead of every event (analytics/base_events.py)
        with_steps = (
            slices_in(app, from_datetime, to_datetime)
            .filter(names__overlap=[name for names in step_names for name in names])
            .exclude(session_id__isnull=True)
            .exclude(session_id="")
        )
        if country and country_list:
            with_steps = with_steps.filter(country__in=country_list)
        if platform and platform_list:
            with_steps = with_steps.filter(platform__in=platform_list)
        total_sessions = session_count(with_steps)

        # Format response (same API contract as before)
        funnel_data = [{"step": steps[i], "count": step_counts[i]} for i in range(len(steps))]

        response_data = {
            "app_name": app.name,
            "funnel": funnel_data,
            "total_sessions_analyzed": total_sessions,
        }

        # Include step timeout info if specified
        if window_minutes:
            response_data["step_timeout_minutes"] = int(window_minutes)

        # PERF-006: Cache funnel results for 2 minutes, under the key read above
        cache_ttl = getattr(settings, "CACHE_TTL_FUNNEL", 120)
        cache.set(cache_key, response_data, timeout=cache_ttl)

        return Response(response_data)


class EventTypesView(APIView):
    """
    GET /api/v1/events/event-types/ - Get all distinct event names for an app

    Convenience endpoint to discover what events are being tracked.
    """

    share_links = True  # a share link's dashboard reads it (teams/)
    authentication_classes = APP_OWNER
    permission_classes = [HasValidAppKey]

    @swagger_auto_schema(
        operation_description="Get all distinct event types being tracked for your app",
        manual_parameters=[
            openapi.Parameter(
                "X-App-Key",
                openapi.IN_HEADER,
                description="App Key for authentication",
                type=openapi.TYPE_STRING,
                required=True,
            ),
        ],
        responses={
            200: openapi.Response(
                description="List of event types",
                examples={
                    "application/json": {
                        "app_name": "My Mobile App",
                        "app_key": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                        "event_types": [
                            "app_open",
                            "product_view",
                            "purchase",
                            "share",
                            "settings_open",
                        ],
                        "count": 5,
                    }
                },
            ),
            401: "Unauthorized - missing or invalid app_key",
        },
    )
    def get(self, request):
        # Get the authenticated app
        app = request.user

        # Every name the app has sent, as the API reference says: one short index read per name,
        # never a scan of its events (analytics/event_groups.py, known_names)
        event_types = known_names(app.id)

        return Response(
            {"app_name": app.name, "event_types": list(event_types), "count": len(event_types)}
        )


class FilterOptionsView(APIView):
    """
    GET /api/v1/events/filter-options/ - Get unique values for all filter fields

    Returns all unique values for each filterable field to populate dropdowns.
    Internal endpoint - used by web dashboard only.
    """

    share_links = True  # a share link's dashboard reads it (teams/)
    authentication_classes = APP_OWNER
    permission_classes = [HasValidAppKey]

    # Exclude from public API documentation
    swagger_schema = None

    @swagger_auto_schema(
        operation_description="Get unique filter values for dropdown population",
        manual_parameters=[
            openapi.Parameter(
                "X-App-Key",
                openapi.IN_HEADER,
                description="App Key for authentication",
                type=openapi.TYPE_STRING,
                required=True,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Unique filter values",
                examples={
                    "application/json": {
                        "app_name": "My Mobile App",
                        "app_key": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                        "filters": {
                            "countries": ["US", "CA", "UK"],
                            "platforms": ["ios", "android"],
                        },
                    }
                },
            ),
            401: "Unauthorized - missing or invalid app_key",
        },
    )
    def get(self, request):
        # Get the authenticated app
        app = request.user

        # PERF-006: Cache filter options for 5 minutes
        # Filter options change rarely, so caching reduces database load significantly
        from django.conf import settings
        from django.core.cache import cache

        cache_key = f"filter_options:{app.id}"
        cached_result = cache.get(cache_key)

        if cached_result is not None:
            return Response(cached_result)

        # Countries and platforms by index probes, event names from known_names: no read of
        # the app's events (analytics/filter_values.py)
        countries, platforms = countries_and_platforms(app.id)
        response_data = {
            "app_name": app.name,
            "filters": {
                "countries": countries,
                "platforms": platforms,
                "event_names": sorted(n for n in known_names(app.id) if n and n.strip()),
            },
        }

        cache_ttl = getattr(settings, "CACHE_TTL_FILTER_OPTIONS", 300)
        cache.set(cache_key, response_data, timeout=cache_ttl)

        return Response(response_data)


# =============================================================================
# SECTION 5: EXPORT & ACTIVITY VIEWS
# =============================================================================


class ExportEventsView(APIView):
    """
    GET /api/v1/events/export/ - Export events in CSV or JSON format

    Query parameters:
        - output: Export format ('csv' or 'json', default: 'csv')
        - from: Start date (YYYY-MM-DD)
        - to: End date (YYYY-MM-DD)
        - event_name: Filter by specific event name
        - country: Filter by country code
        - platform: Filter by platform

    Returns file download with all event data matching the filters.
    Read with the account's secret key (core/api_schema.py publishes it).
    """

    authentication_classes = APP_OWNER
    permission_classes = [HasValidAppKey]

    @swagger_auto_schema(
        operation_description="Export event data in CSV or JSON format with optional filters",
        manual_parameters=[
            openapi.Parameter(
                "X-App-Key",
                openapi.IN_HEADER,
                description="App Key for authentication",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "output",
                openapi.IN_QUERY,
                description="Export format: 'csv' or 'json' (default: csv)",
                type=openapi.TYPE_STRING,
                enum=["csv", "json"],
                required=False,
            ),
            openapi.Parameter(
                "from",
                openapi.IN_QUERY,
                description="Start date in YYYY-MM-DD format",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "to",
                openapi.IN_QUERY,
                description="End date in YYYY-MM-DD format",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "event_name",
                openapi.IN_QUERY,
                description="Filter by event name",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "country",
                openapi.IN_QUERY,
                description="Filter by country code",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "platform",
                openapi.IN_QUERY,
                description="Filter by platform (ios, android, web)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Event data file download",
                examples={
                    "text/csv": "# See response content for CSV data",
                    "application/json": {
                        "metadata": {
                            "app_name": "My Mobile App",
                            "app_key": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                            "export_date": "2025-11-12T10:30:00Z",
                            "date_range": {"from": "2025-11-01", "to": "2025-11-12"},
                            "total_events": 1523,
                            "filters_applied": {},
                        },
                        "events": [
                            {
                                "id": "uuid",
                                "event_name": "app_open",
                                "timestamp": "2025-11-12T10:15:23Z",
                                "session_id": "session_abc123",
                                "country": "US",
                                "platform": "ios",
                            }
                        ],
                    },
                },
            ),
            400: "Bad request - Invalid parameters",
            401: "Unauthorized - Invalid app_key",
        },
    )
    def get(self, request):
        # Get the authenticated app
        app = request.user

        # Get query parameters
        # Note: app_version filter removed (schema reduction)
        export_format = request.query_params.get("output", "csv").lower()
        from_date = request.query_params.get("from")
        to_date = request.query_params.get("to")
        event_name = request.query_params.get("event_name")
        country = request.query_params.get("country")
        platform = request.query_params.get("platform")

        # Validate format
        if export_format not in ["csv", "json"]:
            return Response(
                {"error": 'Invalid output format. Use "csv" or "json"'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Start with events for this app
        events = Event.objects.filter(app=app)

        # Track applied filters for metadata
        filters_applied = {}

        # Apply date filters with guardrails
        # Defaults: if no dates provided, export last EXPORT_MAX_DAYS days.
        max_days = getattr(settings, "EXPORT_MAX_DAYS", 90)
        now = datetime.now(UTC).replace(tzinfo=None)
        if not from_date and not to_date:
            # Default rolling window
            default_from = (now - timedelta(days=max_days - 1)).strftime("%Y-%m-%d")
            default_to = now.strftime("%Y-%m-%d")
            from_date = default_from
            to_date = default_to

        parsed_from = None
        parsed_to = None
        if from_date:
            try:
                parsed_from = datetime.strptime(from_date, "%Y-%m-%d")
                filters_applied["from_date"] = from_date
                events = events.filter(timestamp__gte=parsed_from)
            except ValueError:
                return Response(
                    {"error": "Invalid from date format. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if to_date:
            try:
                parsed_to = datetime.strptime(to_date, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                )
                filters_applied["to_date"] = to_date
                events = events.filter(timestamp__lte=parsed_to)
            except ValueError:
                return Response(
                    {"error": "Invalid to date format. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Enforce maximum date span when both ends are present
        if parsed_from and parsed_to:
            days_span = (parsed_to.date() - parsed_from.date()).days + 1
            if days_span > max_days:
                return Response(
                    {
                        "error": (
                            f"Date range too large: {days_span} days. Maximum allowed is "
                            f"{max_days} days."
                        ),
                        "max_days": max_days,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Apply other filters
        if event_name:
            events = events.filter(event_name=event_name)
            filters_applied["event_name"] = event_name

        if country:
            events = events.filter(country__iexact=country)
            filters_applied["country"] = country

        if platform:
            events = events.filter(platform__iexact=platform)
            filters_applied["platform"] = platform

        # Order by timestamp
        events = events.order_by("-timestamp")

        # Get total count before slicing (for large datasets, consider pagination)
        total_events = events.count()

        # Limit to prevent memory issues (can be adjusted or made configurable)
        MAX_EXPORT_EVENTS = getattr(settings, "EXPORT_MAX_EVENTS", 100000)
        if total_events > MAX_EXPORT_EVENTS:
            return Response(
                {
                    "error": (
                        f"Too many events to export ({total_events}). Maximum is "
                        f"{MAX_EXPORT_EVENTS}. Please apply more specific filters or date range."
                    ),
                    "total_events": total_events,
                    "max_allowed": MAX_EXPORT_EVENTS,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prepare metadata
        metadata = {
            "app_name": app.name,
            "app_slug": app.slug,
            "export_date": datetime.now().isoformat(),
            "date_range": {"from": from_date or "all", "to": to_date or "all"},
            "total_events": total_events,
            "filters_applied": filters_applied,
            "export_format": export_format,
            "limits": {
                "max_days": max_days,
                "max_events": MAX_EXPORT_EVENTS,
            },
        }

        if export_format == "csv":
            # Create CSV response
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            filename = f"respectlytics_{app.slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            response["Content-Disposition"] = f'attachment; filename="{filename}"'

            writer = csv.writer(response)

            # Write metadata as comments
            writer.writerow(["# Respectlytics Analytics Export"])
            writer.writerow([f"# App: {metadata['app_name']}"])
            writer.writerow([f"# Export Date: {metadata['export_date']}"])
            writer.writerow(
                [
                    f"# Date Range: {metadata['date_range']['from']} to "
                    f"{metadata['date_range']['to']}"
                ]
            )
            writer.writerow([f"# Total Events: {metadata['total_events']}"])
            if filters_applied:
                writer.writerow(
                    [f"# Filters: {', '.join([f'{k}={v}' for k, v in filters_applied.items()])}"]
                )
            writer.writerow([])  # Empty line

            # Write CSV header
            writer.writerow(
                ["Event ID", "Event Name", "Timestamp", "Session ID", "Country", "Platform"]
            )

            # Write event data
            for event in events.iterator(chunk_size=1000):  # Use iterator for memory efficiency
                writer.writerow(
                    [
                        str(event.id),
                        event.event_name or "",
                        event.timestamp.isoformat(),
                        event.session_id or "",
                        event.country or "",
                        event.platform or "",
                    ]
                )

            return response

        else:  # JSON format
            # PERF-FIX: Use streaming response for JSON to avoid loading all events into memory
            def generate_json_stream():
                """Generator for streaming JSON response - memory efficient for large exports."""
                # Start with opening brace and metadata
                yield '{\n  "metadata": '
                yield json.dumps(metadata, indent=2).replace("\n", "\n  ")
                yield ',\n  "events": [\n'

                first_event = True
                for event in events.iterator(chunk_size=1000):
                    event_dict = {
                        "id": str(event.id),
                        "event_name": event.event_name,
                        "timestamp": event.timestamp.isoformat(),
                        "session_id": event.session_id,
                        "country": event.country,
                        "platform": event.platform,
                    }

                    if first_event:
                        yield "    " + json.dumps(event_dict)
                        first_event = False
                    else:
                        yield ",\n    " + json.dumps(event_dict)

                # Close the events array and root object
                yield "\n  ]\n}"

            # Create streaming JSON response
            response = StreamingHttpResponse(
                generate_json_stream(), content_type="application/json; charset=utf-8"
            )
            filename = f"respectlytics_{app.slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            response["Content-Disposition"] = f'attachment; filename="{filename}"'

            return response


class RecentActivityView(APIView):
    """
    Lightweight endpoint for polling recent activity.
    Returns summary of new events since a timestamp, optimized for real-time updates.

    GET /api/v1/events/recent-activity/?since=<timestamp>&time_range=<minutes>

    Query parameters:
        - since: ISO timestamp of last update (optional)
        - time_range: Time range in minutes (30, 60, 360, 1440 for 24h). Default: 1440

    Returns:
        - new_event_count: Number of new events since 'since' timestamp
        - last_event_timestamp: Timestamp of most recent event
        - total_in_range: Total events in the selected time range
        - should_refresh: Boolean indicating if UI should fetch full data
        - event_preview: Sample of latest 5 events

    Internal endpoint - used by web dashboard only.
    """

    share_links = True  # a share link's dashboard reads it (teams/)
    authentication_classes = APP_OWNER
    permission_classes = [HasValidAppKey]

    # Exclude from public API documentation
    swagger_schema = None

    @swagger_auto_schema(
        operation_description="Get lightweight summary of recent activity for polling",
        manual_parameters=[
            openapi.Parameter(
                "X-App-Key",
                openapi.IN_HEADER,
                description="App Key for authentication",
                type=openapi.TYPE_STRING,
                required=True,
            ),
            openapi.Parameter(
                "since",
                openapi.IN_QUERY,
                description="ISO timestamp of last poll (e.g., 2025-11-12T10:30:00Z)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "time_range",
                openapi.IN_QUERY,
                description="Time range in minutes: 30, 60, 360, 1440 (default)",
                type=openapi.TYPE_INTEGER,
                enum=[30, 60, 360, 1440],
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Recent activity summary",
                examples={
                    "application/json": {
                        "new_event_count": 5,
                        "last_event_timestamp": "2025-11-12T10:45:30Z",
                        "total_in_range": 234,
                        "should_refresh": True,
                        "time_range_minutes": 1440,
                        "event_preview": [
                            {
                                "event_name": "purchase",
                                "timestamp": "2025-11-12T10:45:30Z",
                                "country": "US",
                            }
                        ],
                        "warnings": [],
                    }
                },
            ),
            400: "Bad request - Invalid parameters",
            401: "Unauthorized - Invalid app_key",
        },
    )
    def get(self, request):
        from django.utils import timezone as django_timezone

        app = request.user

        # Get query parameters
        since_param = request.query_params.get("since")
        time_range_minutes = int(request.query_params.get("time_range", 1440))

        # Validate time_range
        valid_ranges = [30, 60, 360, 1440]
        if time_range_minutes not in valid_ranges:
            return Response(
                {"error": f"Invalid time_range. Must be one of: {valid_ranges}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse 'since' timestamp
        since_timestamp = None
        if since_param:
            try:
                # Parse ISO format timestamp
                since_timestamp = datetime.fromisoformat(since_param.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return Response(
                    {
                        "error": (
                            "Invalid since timestamp. Use ISO format (e.g., 2025-11-12T10:30:00Z)"
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Calculate time window
        now = django_timezone.now()
        time_window_start = now - timedelta(minutes=time_range_minutes)

        # Get events in the time range
        events_in_range = Event.objects.filter(app=app, timestamp__gte=time_window_start).order_by(
            "-timestamp"
        )

        total_in_range = events_in_range.count()

        # Count new events since last poll
        new_event_count = 0
        if since_timestamp:
            new_events = events_in_range.filter(timestamp__gt=since_timestamp)
            new_event_count = new_events.count()

        # Get the most recent event timestamp
        last_event = events_in_range.first()
        last_event_timestamp = last_event.timestamp.isoformat() if last_event else None

        # Get preview of latest events (max 5)
        event_preview = []
        for event in events_in_range[:5]:
            event_preview.append(
                {
                    "event_name": event.event_name,
                    "timestamp": event.timestamp.isoformat(),
                    "country": event.country or "Unknown",
                    "platform": event.platform or "Unknown",
                }
            )

        # Determine if full refresh is needed
        # Refresh if there are new events or significant changes
        should_refresh = new_event_count > 0

        # Check for high traffic and add warnings
        warnings = []
        max_events_threshold = 10000
        if total_in_range > max_events_threshold:
            warnings.append(
                {
                    "type": "high_traffic",
                    "message": (
                        f"High traffic detected ({total_in_range} events in {time_range_minutes} "
                        "min). Consider using a longer time range for better performance."
                    ),
                    "suggested_time_range": min(time_range_minutes * 2, 1440),
                }
            )

        return Response(
            {
                "new_event_count": new_event_count,
                "last_event_timestamp": last_event_timestamp,
                "total_in_range": total_in_range,
                "should_refresh": should_refresh,
                "time_range_minutes": time_range_minutes,
                "event_preview": event_preview,
                "warnings": warnings,
                "server_time": now.isoformat(),
            },
            status=status.HTTP_200_OK,
        )


# NOTE: Conversion Intelligence views (DAUView, ConversionSummaryView,
# TimeToConversionView, StepTimingView) have been moved to conversion/views.py
# as part of the codebase restructuring (TASK-041).
# TimeToConversionView, StepTimingView) have been moved to conversion/views.py


# ============================================================================
# Event Data Deletion Views (Public API)
# ============================================================================


def _build_event_filter(app, data):
    """
    Build a queryset filter dict from deletion request data.
    Returns (filters_dict, error_response_or_None).
    """
    date_from = data.get("date_from")
    date_to = data.get("date_to")

    if not date_from or not date_to:
        return None, Response(
            {"error": "date_from and date_to are required (YYYY-MM-DD format)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        parsed_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        parsed_to = datetime.strptime(date_to, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None, Response(
            {"error": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST
        )

    if parsed_from > parsed_to:
        return None, Response(
            {"error": "date_from must be before or equal to date_to."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    filters = {
        "app": app,
        "timestamp__date__gte": parsed_from,
        "timestamp__date__lte": parsed_to,
    }

    platform = data.get("platform")
    if platform:
        filters["platform"] = platform

    country = data.get("country")
    if country:
        filters["country"] = country

    event_name = data.get("event_name")
    if event_name:
        filters["event_name"] = event_name

    return filters, None


class DeleteEventsPreviewView(APIView):
    """
    Preview how many events match the given filters before deleting.
    Returns the count without performing any deletion.
    """

    authentication_classes = APP_OWNER
    # Deleting, and its history, are the owner's: never a team member's or a link's
    permission_classes = [HasValidAppKey, IsAppOwner]

    @swagger_auto_schema(
        operation_description="""Preview the number of events that would be deleted by the given
filters.

Use this endpoint to check how many events match before calling the delete endpoint.
Date range is required. Platform, country, and event_name are optional additional filters.""",
        manual_parameters=[
            openapi.Parameter(
                "X-App-Key",
                openapi.IN_HEADER,
                description="Your app's API key (UUID)",
                type=openapi.TYPE_STRING,
                required=True,
            ),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["date_from", "date_to"],
            properties={
                "date_from": openapi.Schema(
                    type=openapi.TYPE_STRING, description="Start date (YYYY-MM-DD)"
                ),
                "date_to": openapi.Schema(
                    type=openapi.TYPE_STRING, description="End date (YYYY-MM-DD)"
                ),
                "platform": openapi.Schema(
                    type=openapi.TYPE_STRING, description="Optional: ios, android, web, other"
                ),
                "country": openapi.Schema(
                    type=openapi.TYPE_STRING, description='Optional: ISO country code (e.g., "US")'
                ),
                "event_name": openapi.Schema(
                    type=openapi.TYPE_STRING, description="Optional: specific event name"
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Count of matching events",
                examples={"application/json": {"events_matching": 1523}},
            ),
            400: "Invalid request parameters",
        },
    )
    def post(self, request):
        app = request.user
        filters, error = _build_event_filter(app, request.data)
        if error:
            return error

        count = Event.objects.filter(**filters).count()
        return Response({"events_matching": count}, status=status.HTTP_200_OK)


class DeleteEventsView(APIView):
    """
    Permanently delete events matching the given filters.
    Creates an audit trail entry in the DeletionLog.
    """

    authentication_classes = APP_OWNER
    # Deleting, and its history, are the owner's: never a team member's or a link's
    permission_classes = [HasValidAppKey, IsAppOwner]

    @swagger_auto_schema(
        operation_description="""Permanently delete analytics events matching the given filters.

**This action is irreversible.** All matching events will be permanently removed.

Date range is required. Platform, country, and event_name are optional additional filters.
A DeletionLog entry is created for audit purposes.""",
        manual_parameters=[
            openapi.Parameter(
                "X-App-Key",
                openapi.IN_HEADER,
                description="Your app's API key (UUID)",
                type=openapi.TYPE_STRING,
                required=True,
            ),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["date_from", "date_to"],
            properties={
                "date_from": openapi.Schema(
                    type=openapi.TYPE_STRING, description="Start date (YYYY-MM-DD)"
                ),
                "date_to": openapi.Schema(
                    type=openapi.TYPE_STRING, description="End date (YYYY-MM-DD)"
                ),
                "platform": openapi.Schema(
                    type=openapi.TYPE_STRING, description="Optional: ios, android, web, other"
                ),
                "country": openapi.Schema(
                    type=openapi.TYPE_STRING, description='Optional: ISO country code (e.g., "US")'
                ),
                "event_name": openapi.Schema(
                    type=openapi.TYPE_STRING, description="Optional: specific event name"
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Deletion completed",
                examples={
                    "application/json": {
                        "events_deleted": 1523,
                        "deletion_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    }
                },
            ),
            400: "Invalid request parameters",
        },
    )
    def post(self, request):
        app = request.user
        filters, error = _build_event_filter(app, request.data)
        if error:
            return error

        # Perform deletion
        deleted_count, _ = Event.objects.filter(**filters).delete()

        # Parse dates for the log entry
        parsed_from = datetime.strptime(request.data["date_from"], "%Y-%m-%d").date()
        parsed_to = datetime.strptime(request.data["date_to"], "%Y-%m-%d").date()

        # Create audit trail
        deletion_log = DeletionLog.objects.create(
            app=app,
            app_name=app.name,
            deleted_by=app.user,
            events_deleted=deleted_count,
            filter_date_from=parsed_from,
            filter_date_to=parsed_to,
            filter_platform=request.data.get("platform"),
            filter_country=request.data.get("country"),
            filter_event_name=request.data.get("event_name"),
        )

        # Security log
        log_security_event(
            SecurityEvent.DATA_DELETION,
            user_id=app.user.id,
            reason=f"Deleted {deleted_count} events from app '{app.name}'",
            app_id=str(app.id),
            app_name=app.name,
            deletion_id=str(deletion_log.id),
            date_from=request.data["date_from"],
            date_to=request.data["date_to"],
            platform=request.data.get("platform"),
            country=request.data.get("country"),
            event_name=request.data.get("event_name"),
        )

        return Response(
            {
                "events_deleted": deleted_count,
                "deletion_id": str(deletion_log.id),
            },
            status=status.HTTP_200_OK,
        )


class DeletionHistoryView(APIView):
    """
    Retrieve the deletion history for the authenticated app.
    Returns a list of past deletion log entries for audit purposes.
    """

    authentication_classes = APP_OWNER
    # Deleting, and its history, are the owner's: never a team member's or a link's
    permission_classes = [HasValidAppKey, IsAppOwner]

    @swagger_auto_schema(
        operation_description="""Retrieve the deletion history for this app.

Returns a list of all past event deletions with details about what was deleted and when.
Useful for audit trail and demonstrating deletion request fulfilment.""",
        manual_parameters=[
            openapi.Parameter(
                "X-App-Key",
                openapi.IN_HEADER,
                description="Your app's API key (UUID)",
                type=openapi.TYPE_STRING,
                required=True,
            ),
        ],
        responses={
            200: openapi.Response(
                description="List of deletion log entries",
                examples={
                    "application/json": {
                        "deletions": [
                            {
                                "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                                "deleted_at": "2026-02-10T14:30:00Z",
                                "events_deleted": 1523,
                                "filter_date_from": "2026-01-01",
                                "filter_date_to": "2026-01-31",
                                "filter_platform": None,
                                "filter_country": "US",
                                "filter_event_name": None,
                            }
                        ]
                    }
                },
            ),
        },
    )
    def get(self, request):
        app = request.user
        logs = DeletionLog.objects.filter(app=app).order_by("-deleted_at")

        deletions = []
        for log in logs:
            deletions.append(
                {
                    "id": str(log.id),
                    "deleted_at": log.deleted_at.isoformat(),
                    "events_deleted": log.events_deleted,
                    "filter_date_from": str(log.filter_date_from),
                    "filter_date_to": str(log.filter_date_to),
                    "filter_platform": log.filter_platform,
                    "filter_country": log.filter_country,
                    "filter_event_name": log.filter_event_name,
                }
            )

        return Response({"deletions": deletions}, status=status.HTTP_200_OK)

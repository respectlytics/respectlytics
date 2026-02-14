from rest_framework import serializers
from django.utils import timezone
from .models import App, Event
from .privacy_guards import (
    validate_request_privacy,
    PrivacyValidationError,
    anonymize_session_id,
    DEPRECATED_FIELDS,
)


class AppSerializer(serializers.ModelSerializer):
    """
    Serializer for App model.
    Returns the app_key (UUID) which clients use for authentication.
    """
    app_key = serializers.UUIDField(source='id', read_only=True)

    class Meta:
        model = App
        fields = ['app_key', 'name', 'created_at']
        read_only_fields = ['app_key', 'created_at']


class EventCreateSerializer(serializers.Serializer):
    """
    Serializer for creating events via API.
    
    PRIVACY PROTECTION (Return of Avoidance - ROA):
    This serializer implements strict privacy guards to help developers
    avoid collecting data they don't need.
    - Only allowlisted fields are accepted
    - Session IDs are ephemeral (in-memory only, 2-hour rotation in SDKs)
    - No persistent user identifiers accepted
    - No cross-session tracking possible
    
    See analytics/privacy_guards.py for full validation logic.
    """
    app_key = serializers.UUIDField(required=True)
    event_name = serializers.CharField(required=True, max_length=255, allow_blank=False)
    timestamp = serializers.DateTimeField(required=False)
    country = serializers.CharField(max_length=2, required=False, allow_null=True, allow_blank=True)
    region = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    device_type = serializers.CharField(max_length=50, required=False, allow_null=True, allow_blank=True)
    os_version = serializers.CharField(max_length=50, required=False, allow_null=True, allow_blank=True)
    session_id = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    platform = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)
    app_version = serializers.CharField(max_length=50, required=False, allow_null=True, allow_blank=True)
    locale = serializers.CharField(max_length=10, required=False, allow_null=True, allow_blank=True)
    screen = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)

    def validate(self, attrs):
        """
        Run privacy validation before standard field validation.
        
        This is the first line of defense - we reject requests with
        forbidden fields before any other processing occurs.
        """
        # Get the raw request data for privacy validation
        # initial_data contains ALL fields sent, not just declared ones
        raw_data = self.initial_data if hasattr(self, 'initial_data') else {}
        
        # Get app_key for logging (if present)
        app_key_str = str(raw_data.get('app_key', '')) if raw_data.get('app_key') else None
        
        try:
            validate_request_privacy(raw_data, app_key_for_logging=app_key_str)
        except PrivacyValidationError as e:
            # Convert to DRF validation error with helpful details
            raise serializers.ValidationError({
                'detail': 'Invalid request',
                'code': e.code,
                'reason': e.reason
            })
        
        return attrs

    def validate_app_key(self, value):
        """Validate that the app exists."""
        try:
            app = App.objects.get(id=value)
            return app
        except App.DoesNotExist:
            raise serializers.ValidationError("Invalid app_key. App does not exist.")

    def validate_event_name(self, value):
        """Ensure event_name is not empty."""
        if not value or not value.strip():
            raise serializers.ValidationError("event_name cannot be empty.")
        return value.strip()

    def create(self, validated_data):
        """
        Create and return a new Event instance.

        PRIVACY PROCESSING (Session-Based Analytics):
        - Deprecated fields are silently ignored (not stored) for backwards compatibility
        - Session IDs are anonymized using daily rotation before storage
        - The original client-provided session_id is never stored
        - This enables single-session funnel analysis without cross-session tracking
        """
        app = validated_data.pop('app_key')

        # Use current time if timestamp not provided
        if 'timestamp' not in validated_data or validated_data['timestamp'] is None:
            validated_data['timestamp'] = timezone.now()

        # SCHEMA REDUCTION: Remove deprecated fields before saving
        # These fields are accepted by the API for backwards compatibility with existing SDKs,
        # but are not stored in the database (silently ignored).
        # Deprecated: device_type, os_version, app_version, locale, region, screen
        for field in DEPRECATED_FIELDS:
            validated_data.pop(field, None)

        # Clean up empty string values to None for remaining fields
        for field in ['country', 'session_id', 'platform']:
            if field in validated_data and validated_data[field] == '':
                validated_data[field] = None

        # PRIVACY: Anonymize session_id with daily rotation
        # The original session_id is discarded and only the hash is stored.
        # This prevents cross-day session tracking while preserving intra-day analysis.
        if validated_data.get('session_id'):
            validated_data['session_id'] = anonymize_session_id(
                session_id=validated_data['session_id'],
                app_id=str(app.id)
            )

        event = Event.objects.create(app=app, **validated_data)
        return event


class EventSerializer(serializers.ModelSerializer):
    """
    Serializer for Event model (read operations).
    
    Session-Based Analytics:
    - Session IDs are ephemeral (2-hour rotation, regenerate on app restart)
    - No persistent user identifiers stored
    - Enables single-session funnel analysis without cross-session tracking
    """
    app_name = serializers.CharField(source='app.name', read_only=True)

    class Meta:
        model = Event
        fields = ['id', 'app_name', 'event_name', 'timestamp', 'country',
                  'session_id', 'platform']

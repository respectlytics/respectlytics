import uuid
from django.db import models
from django.contrib.auth.models import User


class App(models.Model):
    """
    Represents a mobile application that sends analytics events.
    Each app has a unique UUID used as an API key for authentication.
    Every app must belong to a registered user.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='apps')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Conversion Intelligence preferences (TASK-040)
    # List of event names that the user considers "conversion events"
    # Stored as JSON array, e.g., ["purchase", "subscription_started"]
    # Server-side storage (not browser localStorage) for GDPR compliance
    preferred_conversion_events = models.JSONField(
        default=list, 
        blank=True,
        help_text="Event names to use as conversion events in analytics dashboards"
    )
    
    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while App.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)
    
    def regenerate_key(self):
        """
        Regenerate the API key (UUID) for this app.
        Useful for key rotation or security incidents.
        
        Strategy: Use raw SQL to update the primary key and foreign key references.
        Django's ORM doesn't support updating primary keys, so we use raw SQL.
        We must manually update Event.app_id foreign keys since CASCADE only applies to DELETE.
        
        Note: SQLite stores UUIDs as strings without hyphens, so we must convert them.
        """
        from django.db import transaction, connection
        
        old_key = str(self.id)
        new_key = str(uuid.uuid4())
        
        # SQLite stores UUIDs without hyphens (as char(32), not char(36))
        # Convert UUID strings to the database format
        old_key_db = old_key.replace('-', '')
        new_key_db = new_key.replace('-', '')
        
        with transaction.atomic():
            # Use raw SQL to update the primary key and related foreign keys
            with connection.cursor() as cursor:
                # First, update all Event records to point to the new key
                cursor.execute(
                    "UPDATE analytics_event SET app_id = %s WHERE app_id = %s",
                    [new_key_db, old_key_db]
                )
                
                # Then update the app's primary key
                cursor.execute(
                    "UPDATE analytics_app SET id = %s WHERE id = %s",
                    [new_key_db, old_key_db]
                )
            
            # Update this instance's ID to reflect the new key
            # Don't call refresh_from_db() because it will fail to find the object
            # (it uses the current PK which was already changed in the DB)
            self.id = new_key
            self.pk = new_key
        
        return old_key, new_key

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'App'
        verbose_name_plural = 'Apps'

    def __str__(self):
        return f"{self.name} ({self.id})"


class Event(models.Model):
    """
    Represents an anonymized analytics event from a mobile app.
    
    PRIVACY MODEL (Return of Avoidance - ROA):
    - Only 5 fields stored: event_name, timestamp, platform, country, session_id
    - No persistent user identifiers
    - Session IDs are ephemeral (in-memory only, 2-hour rotation in SDKs)
    - No cross-session tracking possible
    - Transparent about what is collected, defensible by design
    
    DEPRECATED FIELDS (accepted by API but not stored):
    - app_version, os_version, device_type, locale, region, screen
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    app = models.ForeignKey(App, on_delete=models.CASCADE, related_name='events')
    event_name = models.CharField(max_length=255)
    timestamp = models.DateTimeField()
    
    # Country - derived from IP (IP never stored)
    country = models.CharField(max_length=2, null=True, blank=True)  # ISO country code (e.g., "US")
    
    # Platform - ios, android, web, other
    platform = models.CharField(max_length=20, null=True, blank=True)
    
    # Session ID - ephemeral identifier for single-session analytics
    # Generated in-memory by SDK, rotates every 2 hours or on app restart
    # Enables funnel analysis within a single session, no cross-session tracking
    session_id = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Event'
        verbose_name_plural = 'Events'
        indexes = [
            # Core indexes
            models.Index(fields=['app', 'timestamp']),
            models.Index(fields=['event_name']),
            models.Index(fields=['timestamp']),
            
            # Session-based analytics indexes
            models.Index(fields=['app', 'event_name', 'timestamp']),  # Event type + time range queries
            models.Index(fields=['app', 'session_id', 'timestamp']),  # Session/funnel analysis
            models.Index(fields=['app', 'timestamp', 'country']),     # Geo + time range queries
            models.Index(fields=['app', 'session_id']),               # Session lookups
        ]

    def __str__(self):
        return f"{self.event_name} - {self.app.name} @ {self.timestamp}"


class DeletionLog(models.Model):
    """
    Persistent audit trail for event data deletions.
    
    Allows app owners to demonstrate to auditors that deletion requests
    were fulfilled, with details about what was deleted and when.
    
    Lifecycle:
    - Created when events are deleted (via dashboard or API)
    - Survives app deletion (SET_NULL on app FK, app_name snapshot preserved)
    - Deleted when the user account is deleted (CASCADE on deleted_by FK)
    - Cleaned up after 2 years by scheduled task (same as event retention)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # App reference: SET_NULL so history survives app deletion
    app = models.ForeignKey(
        App,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deletion_logs',
    )
    # Snapshot of app name at deletion time (readable even after app is deleted)
    app_name = models.CharField(max_length=255)
    
    # Who performed the deletion
    deleted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='deletion_logs',
    )
    deleted_at = models.DateTimeField(auto_now_add=True)
    
    # How many events were removed
    events_deleted = models.PositiveIntegerField()
    
    # Filters used (date range is always required)
    filter_date_from = models.DateField()
    filter_date_to = models.DateField()
    filter_platform = models.CharField(max_length=20, null=True, blank=True)
    filter_country = models.CharField(max_length=2, null=True, blank=True)
    filter_event_name = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        ordering = ['-deleted_at']
        verbose_name = 'Deletion Log'
        verbose_name_plural = 'Deletion Logs'

    def __str__(self):
        return f"Deleted {self.events_deleted} events from {self.app_name} on {self.deleted_at}"

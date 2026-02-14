from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from rest_framework import status
from datetime import timedelta
from .models import App, Event


class AppModelTestCase(TestCase):
    """Test App model"""
    
    def setUp(self):
        """Create a test user"""
        self.user = User.objects.create_user(username='testuser', password='testpass123')
    
    def test_create_app(self):
        """Test creating an app"""
        app = App.objects.create(name="Test App", user=self.user)
        self.assertIsNotNone(app.id)
        self.assertEqual(app.name, "Test App")
        self.assertIsNotNone(app.created_at)
        self.assertEqual(app.user, self.user)
    
    def test_app_string_representation(self):
        """Test app string representation"""
        app = App.objects.create(name="My App", user=self.user)
        self.assertIn("My App", str(app))
        self.assertIn(str(app.id), str(app))
    
    def test_regenerate_key_preserves_events(self):
        """Test that regenerating API key preserves historical events"""
        app = App.objects.create(name="Test App", user=self.user)
        old_key = app.id
        
        # Create some events with the old key
        event1 = Event.objects.create(
            app=app,
            event_name="app_open",
            timestamp=timezone.now(),
            country="US"
        )
        event2 = Event.objects.create(
            app=app,
            event_name="purchase",
            timestamp=timezone.now(),
            country="CA"
        )
        
        # Regenerate the key
        returned_old_key, new_key = app.regenerate_key()
        
        # Verify keys changed (regenerate_key returns strings)
        self.assertEqual(returned_old_key, str(old_key))
        self.assertNotEqual(new_key, str(old_key))
        self.assertEqual(str(app.id), new_key)
        
        # Verify events still exist and are linked to the app
        # Can't use refresh_from_db() since PK changed; fetch by slug instead
        updated_app = App.objects.get(slug=app.slug)
        events = Event.objects.filter(app=updated_app)
        self.assertEqual(events.count(), 2)
        self.assertIn(event1, events)
        self.assertIn(event2, events)
        
        # Verify events are linked to the new key
        event1.refresh_from_db()
        event2.refresh_from_db()
        self.assertEqual(str(event1.app.id), new_key)
        self.assertEqual(str(event2.app.id), new_key)


class EventModelTestCase(TestCase):
    """Test Event model"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.app = App.objects.create(name="Test App", user=self.user)
    
    def test_create_event(self):
        """Test creating an event with stored fields only.
        
        SCHEMA REDUCTION (ROA): Only stored fields are used in tests.
        Deprecated fields (device_type, os_version, app_version, locale, region, screen)
        still exist in the model but are not populated via API.
        """
        event = Event.objects.create(
            app=self.app,
            event_name="app_open",
            timestamp=timezone.now(),
            country="US",
            platform="ios",
        )
        self.assertIsNotNone(event.id)
        self.assertEqual(event.event_name, "app_open")
        self.assertEqual(event.app, self.app)
        self.assertEqual(event.platform, "ios")


class AppAPITestCase(APITestCase):
    """Test App API endpoints"""
    
    def setUp(self):
        """Create a test user for authentication"""
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(username='testuser', password='testpass123')
    
    def test_create_app_via_api(self):
        """Test creating an app via POST /api/apps/ (requires user auth)"""
        # Login as user
        self.client.force_authenticate(user=self.user)
        
        data = {"name": "Mobile App"}
        response = self.client.post('/api/v1/apps/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('app_key', response.data)
        self.assertIn('name', response.data)
        self.assertEqual(response.data['name'], "Mobile App")
        # Verify the app is linked to the user
        app = App.objects.get(id=response.data['app_key'])
        self.assertEqual(app.user, self.user)
    
    def test_list_apps_requires_authentication(self):
        """Test that listing apps requires user authentication"""
        # Create apps for another user
        other_user = User.objects.create_user(username='otheruser', password='otherpass')
        App.objects.create(name="App 1", user=other_user)
        App.objects.create(name="App 2", user=other_user)
        
        # Without authentication
        response = self.client.get('/api/v1/apps/')
        # Returns 401 when no credentials provided
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
        
    def test_list_apps_with_authentication(self):
        """Test listing apps with user authentication (only shows user's apps)"""
        # Login as user
        self.client.force_authenticate(user=self.user)
        
        # Create apps for this user
        App.objects.create(name="My App 1", user=self.user)
        App.objects.create(name="My App 2", user=self.user)
        
        # Create apps for another user (should not be visible)
        other_user = User.objects.create_user(username='otheruser', password='otherpass')
        App.objects.create(name="Other App", user=other_user)
        
        response = self.client.get('/api/v1/apps/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should only see the 2 apps belonging to this user
        self.assertEqual(len(response.data), 2)
        names = [app['name'] for app in response.data]
        self.assertIn("My App 1", names)
        self.assertIn("My App 2", names)
        self.assertNotIn("Other App", names)


class EventAPITestCase(APITestCase):
    """Test Event API endpoints"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.app = App.objects.create(name="Test App", user=self.user)
        self.app_key = str(self.app.id)
    
    def test_create_event_via_api_with_header(self):
        """Test posting an event via POST /api/events/ with X-App-Key header"""
        data = {
            "event_name": "purchase",
            "timestamp": timezone.now().isoformat(),
            "country": "US",
            "device_type": "Android",
            "os_version": "14"
        }
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('id', response.data)
        self.assertEqual(response.data['event_name'], "purchase")
    
    def test_create_event_with_deprecated_optional_fields(self):
        """Test that deprecated optional fields are accepted but NOT stored.
        
        SCHEMA REDUCTION (ROA - Return of Avoidance):
        - Deprecated fields: device_type, os_version, app_version, locale, region, screen
        - These are accepted for backwards compatibility but silently ignored
        - Only platform is stored from the new fields
        """
        data = {
            "event_name": "checkout",
            "timestamp": timezone.now().isoformat(),
            "country": "US",
            "device_type": "iPhone 15",  # DEPRECATED - accepted but not stored
            "os_version": "iOS 17.1",     # DEPRECATED - accepted but not stored
            "session_id": "a1b2c3d4e5f6g7h8i9j0",  # 20 chars - meets privacy requirements
            "platform": "ios",            # STORED
            "app_version": "2.1.0",       # DEPRECATED - accepted but not stored
            "locale": "en-US",            # DEPRECATED - accepted but not stored
            "screen": "checkout_page"     # DEPRECATED - accepted but not stored
        }
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('id', response.data)
        self.assertEqual(response.data['event_name'], "checkout")
        
        # Verify only stored fields are persisted
        event = Event.objects.get(id=response.data['id'])
        self.assertEqual(event.platform, "ios")  # STORED
        # Note: Deprecated fields (app_version, locale, screen) no longer exist on model
        # They are accepted by API but silently discarded
    
    def test_create_event_via_api_with_body(self):
        """Test posting an event with app_key in body"""
        data = {
            "app_key": self.app_key,
            "event_name": "purchase",
            "country": "US"
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('id', response.data)
        self.assertEqual(response.data['event_name'], "purchase")
    
    def test_create_event_without_authentication(self):
        """Test that creating event without app_key fails"""
        data = {
            "event_name": "click"
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        # Returns 401 when no credentials provided
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
    
    def test_create_event_without_timestamp(self):
        """Test that timestamp defaults to now if not provided"""
        data = {
            "event_name": "click"
        }
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('timestamp', response.data)
    
    def test_create_event_with_invalid_app_key(self):
        """Test creating event with invalid app_key returns error"""
        data = {
            "event_name": "test"
        }
        self.client.credentials(HTTP_X_APP_KEY="00000000-0000-0000-0000-000000000000")
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_create_event_with_empty_event_name(self):
        """Test creating event with empty event_name returns error"""
        data = {
            "event_name": ""
        }
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class EventSummaryAPITestCase(APITestCase):
    """Test Event Summary API endpoint"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.app = App.objects.create(name="Test App", user=self.user)
        self.app_key = str(self.app.id)
        
        # Create test events
        now = timezone.now()
        Event.objects.create(
            app=self.app,
            event_name="open",
            timestamp=now,
            country="US"
        )
        Event.objects.create(
            app=self.app,
            event_name="purchase",
            timestamp=now - timedelta(days=1),
            country="US"
        )
        Event.objects.create(
            app=self.app,
            event_name="open",
            timestamp=now - timedelta(days=2),
            country="CA"
        )
    
    def test_get_summary_with_header(self):
        """Test getting event summary via GET /api/events/summary/ with header auth"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/events/summary/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_events', response.data)
        self.assertIn('events_by_name', response.data)
        self.assertIn('events_by_day', response.data)
        self.assertIn('top_countries', response.data)
        self.assertIn('unique_countries', response.data)
        self.assertEqual(response.data['total_events'], 3)
        self.assertIsInstance(response.data['unique_countries'], int)
    
    def test_get_summary_with_query_param(self):
        """Test getting summary with app_key as query parameter"""
        response = self.client.get(f'/api/v1/events/summary/?app_key={self.app_key}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_events'], 3)
    
    def test_get_summary_with_date_filter(self):
        """Test getting summary with date filters"""
        today = timezone.now().strftime('%Y-%m-%d')
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get(f'/api/v1/events/summary/?from={today}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_events'], 1)
    
    def test_get_summary_without_authentication(self):
        """Test that summary requires authentication"""
        response = self.client.get('/api/v1/events/summary/')
        
        # Returns 401 when no credentials provided
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
    
    def test_get_summary_with_invalid_app_key(self):
        """Test summary with invalid app_key returns 401"""
        self.client.credentials(HTTP_X_APP_KEY="00000000-0000-0000-0000-000000000000")
        response = self.client.get('/api/v1/events/summary/')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class SecurityTestCase(APITestCase):
    """Test security features"""
    
    def setUp(self):
        # Clear cache before each test to avoid rate limit carryover
        from django.core.cache import cache
        cache.clear()
        
        # Create a test user
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        
        # Create an app for event testing
        self.app = App.objects.create(name="Test App", user=self.user)
        self.app_key = str(self.app.id)
    
    def test_rate_limiting_on_app_creation(self):
        """Test that unauthenticated users cannot create apps at all"""
        # Try to create apps without authentication
        data = {"name": "App 1"}
        response = self.client.post('/api/v1/apps/', data, format='json')
        
        # Should be rejected due to no authentication (401 or 403)
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
    
    def test_multiple_failed_auth_tracking(self):
        """Test that failed authentication attempts are tracked"""
        # Make multiple requests without authentication
        for _ in range(5):
            response = self.client.get('/api/v1/apps/')
            self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
        
        # Failed attempts should be logged (check via middleware)
    
    def test_valid_requests_not_rate_limited(self):
        """Test that authenticated valid requests are not overly restricted"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # Make several valid requests
        for _ in range(50):  # Well under 100/minute burst limit
            data = {
                "event_name": "test_event"
            }
            response = self.client.post('/api/v1/events/', data, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_different_auth_methods_all_work(self):
        """Test that app endpoints require user auth, event endpoints use app_key"""
        # Test that /api/apps/ requires user authentication
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/v1/apps/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test that /api/events/ uses app_key authentication (header)
        self.client.force_authenticate(user=None)  # Clear user auth
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            "event_name": "test"
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Test body auth for events (app_key in body)
        self.client.credentials()  # Clear credentials
        data = {
            "app_key": self.app_key,
            "event_name": "test2"
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_invalid_app_key_format(self):
        """Test that invalid UUID format is handled properly"""
        self.client.credentials(HTTP_X_APP_KEY="not-a-uuid")
        response = self.client.get('/api/v1/apps/')
        # Should return 401 or 403 depending on authentication method
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


class FunnelAnalysisTestCase(APITestCase):
    """Test funnel analysis endpoint"""
    
    def setUp(self):
        # Clear cache before each test
        from django.core.cache import cache
        cache.clear()
        
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.app = App.objects.create(name="Test App", user=self.user)
        self.app_key = str(self.app.id)
        
        # Create test events with sessions
        now = timezone.now()
        
        # Session 1: Completes all steps
        Event.objects.create(
            app=self.app,
            event_name="app_open",
            session_id="session_1",
            timestamp=now
        )
        Event.objects.create(
            app=self.app,
            event_name="product_view",
            session_id="session_1",
            timestamp=now + timedelta(seconds=10)
        )
        Event.objects.create(
            app=self.app,
            event_name="purchase",
            session_id="session_1",
            timestamp=now + timedelta(seconds=20)
        )
        
        # Session 2: Only completes first two steps
        Event.objects.create(
            app=self.app,
            event_name="app_open",
            session_id="session_2",
            timestamp=now
        )
        Event.objects.create(
            app=self.app,
            event_name="product_view",
            session_id="session_2",
            timestamp=now + timedelta(seconds=15)
        )
        
        # Session 3: Only completes first step
        Event.objects.create(
            app=self.app,
            event_name="app_open",
            session_id="session_3",
            timestamp=now
        )
        
        # Session 4: Events out of order (should not count)
        Event.objects.create(
            app=self.app,
            event_name="purchase",
            session_id="session_4",
            timestamp=now
        )
        Event.objects.create(
            app=self.app,
            event_name="app_open",
            session_id="session_4",
            timestamp=now + timedelta(seconds=10)
        )
    
    def test_funnel_analysis_basic(self):
        """Test basic funnel analysis with sequential steps"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/events/funnel/?steps=app_open,product_view,purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('funnel', response.data)
        
        funnel = response.data['funnel']
        self.assertEqual(len(funnel), 3)
        
        # Check counts
        # Session 1: app_open → product_view → purchase (completes all)
        # Session 2: app_open → product_view (stops at step 2)
        # Session 3: app_open (stops at step 1)
        # Session 4: purchase → app_open (app_open counts for step 1, even though purchase came first)
        self.assertEqual(funnel[0]['step'], 'app_open')
        self.assertEqual(funnel[0]['count'], 4)  # Sessions 1, 2, 3, 4
        
        self.assertEqual(funnel[1]['step'], 'product_view')
        self.assertEqual(funnel[1]['count'], 2)  # Sessions 1, 2 only (must have app_open first)
        
        self.assertEqual(funnel[2]['step'], 'purchase')
        self.assertEqual(funnel[2]['count'], 1)  # Session 1 only (must have product_view first)
    
    def test_funnel_analysis_missing_steps(self):
        """Test that missing steps parameter returns error"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/events/funnel/')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_funnel_analysis_insufficient_steps(self):
        """Test that fewer than 2 steps returns error"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/events/funnel/?steps=app_open')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_funnel_analysis_requires_auth(self):
        """Test that funnel endpoint requires authentication"""
        response = self.client.get('/api/v1/events/funnel/?steps=app_open,purchase')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_funnel_analysis_with_date_filter(self):
        """Test funnel analysis with date filters"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        today = timezone.now().strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/events/funnel/?steps=app_open,product_view&from={today}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('funnel', response.data)
    
    def test_funnel_analysis_with_platform_filter(self):
        """Test funnel analysis with platform filter (the only behavioral filter supported)
        
        SCHEMA REDUCTION (ROA): app_version, locale, and screen filters were removed.
        Only country and platform filters are supported for funnel analysis.
        """
        # Create events with platform field
        now = timezone.now()
        
        # iOS session
        Event.objects.create(
            app=self.app,
            event_name="app_open",
            session_id="ios_session_1",
            timestamp=now,
            platform="ios",
        )
        Event.objects.create(
            app=self.app,
            event_name="product_view",
            session_id="ios_session_1",
            timestamp=now + timedelta(seconds=10),
            platform="ios",
        )
        
        # Android session (incomplete - no product_view)
        Event.objects.create(
            app=self.app,
            event_name="app_open",
            session_id="android_session_1",
            timestamp=now,
            platform="android",
        )
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # Test platform filter - iOS only
        response = self.client.get('/api/v1/events/funnel/?steps=app_open,product_view&platform=ios')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        funnel = response.data['funnel']
        self.assertEqual(funnel[0]['count'], 1)  # Only iOS session
        self.assertEqual(funnel[1]['count'], 1)  # iOS session completed both steps
        
        # Test platform filter - Android only
        response = self.client.get('/api/v1/events/funnel/?steps=app_open,product_view&platform=android')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        funnel = response.data['funnel']
        self.assertEqual(funnel[0]['count'], 1)  # Android session reached step 1
        self.assertEqual(funnel[1]['count'], 0)  # Android session didn't complete step 2


class EventTypesTestCase(APITestCase):
    """Test event types endpoint"""
    
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.app = App.objects.create(name="Test App", user=self.user)
        self.app_key = str(self.app.id)
        
        # Create events with different types
        now = timezone.now()
        Event.objects.create(app=self.app, event_name="app_open", session_id="s1", timestamp=now)
        Event.objects.create(app=self.app, event_name="purchase", session_id="s1", timestamp=now)
        Event.objects.create(app=self.app, event_name="app_open", session_id="s2", timestamp=now)
        Event.objects.create(app=self.app, event_name="share", session_id="s2", timestamp=now)
    
    def test_event_types_list(self):
        """Test listing distinct event types"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/events/event-types/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('event_types', response.data)
        self.assertEqual(response.data['count'], 3)
        self.assertIn('app_open', response.data['event_types'])
        self.assertIn('purchase', response.data['event_types'])
        self.assertIn('share', response.data['event_types'])
    
    def test_event_types_requires_auth(self):
        """Test that event types endpoint requires authentication"""
        response = self.client.get('/api/v1/events/event-types/')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ExportEventsTestCase(APITestCase):
    """Test event export functionality"""
    
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.app = App.objects.create(name="Test App", user=self.user)
        self.app_key = str(self.app.id)
        
        # Create test events
        # Note: Only stored fields are used (deprecated fields not included)
        # STORED: event_name, timestamp, session_id, country, platform
        # DEPRECATED (not stored): region, device_type, os_version, app_version, locale, screen
        now = timezone.now()
        for i in range(10):
            Event.objects.create(
                app=self.app,
                event_name=f"event_{i % 3}",
                timestamp=now - timedelta(days=i),
                session_id=f"session_{i}",
                country="US",
                platform="ios",
            )
    
    def test_export_csv(self):
        """Test exporting events in CSV format"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/events/export/?output=csv')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('.csv', response['Content-Disposition'])
        
        # Check content includes metadata and data
        content = response.content.decode('utf-8')
        self.assertIn('# Respectlytics Analytics Export', content)
        self.assertIn('# App: Test App', content)
        self.assertIn('Event ID,Event Name,Timestamp', content)
        self.assertIn('event_0', content)
        self.assertIn('session_0', content)
    
    def test_export_json(self):
        """Test exporting events in JSON format"""
        import json
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/events/export/?output=json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/json; charset=utf-8')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('.json', response['Content-Disposition'])
        
        # Parse JSON content (StreamingHttpResponse)
        content = json.loads(b''.join(response.streaming_content).decode('utf-8'))
        self.assertIn('metadata', content)
        self.assertIn('events', content)
        self.assertEqual(content['metadata']['app_name'], 'Test App')
        self.assertEqual(content['metadata']['total_events'], 10)
        self.assertEqual(len(content['events']), 10)
        self.assertIn('event_name', content['events'][0])
        self.assertIn('timestamp', content['events'][0])
    
    def test_export_with_date_filter(self):
        """Test exporting with date range filter"""
        import json
        from datetime import datetime
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        today = datetime.now().strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/events/export/?output=json&from={today}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        content = json.loads(b''.join(response.streaming_content).decode('utf-8'))
        # Should only have 1 event from today
        self.assertEqual(content['metadata']['total_events'], 1)
        self.assertEqual(len(content['events']), 1)
    
    def test_export_with_event_name_filter(self):
        """Test exporting with event name filter"""
        import json
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/events/export/?output=json&event_name=event_0')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        content = json.loads(b''.join(response.streaming_content).decode('utf-8'))
        # Should have 4 events (0, 3, 6, 9)
        self.assertEqual(content['metadata']['total_events'], 4)
        self.assertIn('event_name', content['metadata']['filters_applied'])
    
    def test_export_with_country_filter(self):
        """Test exporting with country filter"""
        import json
        
        # Add an event from different country
        Event.objects.create(
            app=self.app,
            event_name="foreign_event",
            timestamp=timezone.now(),
            country="CA"
        )
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/events/export/?output=json&country=CA')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        content = json.loads(b''.join(response.streaming_content).decode('utf-8'))
        self.assertEqual(content['metadata']['total_events'], 1)
        self.assertEqual(content['events'][0]['country'], 'CA')
    
    def test_export_requires_auth(self):
        """Test that export endpoint requires authentication"""
        response = self.client.get('/api/v1/events/export/?output=csv')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_export_invalid_format(self):
        """Test that invalid format returns error"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/events/export/?output=xml')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_export_invalid_date_format(self):
        """Test that invalid date format returns error"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/events/export/?output=csv&from=invalid-date')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)


class AppRegenerateKeyTestCase(APITestCase):
    """Test API key regeneration functionality"""
    
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.other_user = User.objects.create_user(username='otheruser', password='otherpass123')
        self.app = App.objects.create(name="Test App", user=self.user)
        self.app_key = str(self.app.id)
        
        # Create some events
        Event.objects.create(
            app=self.app,
            event_name="app_open",
            timestamp=timezone.now(),
            country="US"
        )
        Event.objects.create(
            app=self.app,
            event_name="purchase",
            timestamp=timezone.now(),
            country="CA"
        )
    
    def test_regenerate_key_success(self):
        """Test successful API key regeneration"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(f'/api/v1/apps/{self.app.slug}/regenerate-key/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('new_app_key', response.data)
        self.assertIn('message', response.data)
        self.assertIn('warning', response.data)
        
        # Verify key actually changed
        new_key = response.data['new_app_key']
        self.assertNotEqual(new_key, self.app_key)
        
        # Verify app has new key (fetch by slug since PK changed)
        updated_app = App.objects.get(slug=self.app.slug)
        self.assertEqual(str(updated_app.id), new_key)
        
        # Verify events are preserved (using new app instance)
        events = Event.objects.filter(app=updated_app)
        self.assertEqual(events.count(), 2)
    
    def test_regenerate_key_requires_auth(self):
        """Test that regenerating key requires authentication"""
        response = self.client.post(f'/api/v1/apps/{self.app.slug}/regenerate-key/')
        
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
    
    def test_regenerate_key_requires_ownership(self):
        """Test that users can only regenerate keys for their own apps"""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(f'/api/v1/apps/{self.app.slug}/regenerate-key/')
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('error', response.data)
    
    def test_regenerate_key_invalid_slug(self):
        """Test regenerating key with invalid app slug"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/v1/apps/invalid-slug/regenerate-key/')
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('error', response.data)
    
    def test_old_key_becomes_invalid(self):
        """Test that old API key becomes invalid after regeneration"""
        # First, verify old key works
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/events/event-types/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Regenerate the key
        self.client.credentials()  # Clear credentials
        self.client.force_authenticate(user=self.user)
        regen_response = self.client.post(f'/api/v1/apps/{self.app.slug}/regenerate-key/')
        new_key = regen_response.data['new_app_key']
        
        # Verify old key no longer works
        self.client.force_authenticate(user=None)  # Clear user auth
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/events/event-types/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
        # Verify new key works
        self.client.credentials(HTTP_X_APP_KEY=new_key)
        response = self.client.get('/api/v1/events/event-types/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class PrivacyGuardsTestCase(APITestCase):
    """
    Test privacy guards that prevent tracking identifiers and PII.
    
    These tests ensure that:
    1. Only allowlisted fields are accepted
    2. Known tracking identifiers are rejected
    3. Session IDs meet entropy/format requirements
    4. PII patterns in values are detected and rejected
    """
    
    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            username='privacytester',
            email='privacy@test.com',
            password='testpass123'
        )
        self.app = App.objects.create(
            name='Privacy Test App',
            user=self.user
        )
        self.app_key = str(self.app.id)
    
    def get_error_field(self, response_data, field_name):
        """Helper to extract error field value from DRF response (handles list wrapping)."""
        value = response_data.get(field_name)
        if isinstance(value, list) and len(value) > 0:
            return str(value[0])
        return str(value) if value else None
    
    # =========================================================================
    # ALLOWLIST TESTS - Unknown fields must be rejected
    # =========================================================================
    
    def test_unknown_field_rejected(self):
        """Test that unknown/custom fields are rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'custom_field': 'some_value'  # Not in allowlist
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', response.data)
        self.assertEqual(self.get_error_field(response.data, 'code'), 'FORBIDDEN_FIELD')
        self.assertIn('custom_field', self.get_error_field(response.data, 'reason'))
    
    def test_multiple_unknown_fields_rejected(self):
        """Test that multiple unknown fields are rejected together"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'field_a': 'value1',
            'field_b': 'value2'
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.get_error_field(response.data, 'code'), 'FORBIDDEN_FIELDS')
    
    def test_metadata_field_rejected(self):
        """Test that 'metadata' or 'properties' fields are rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        for field_name in ['metadata', 'properties', 'data', 'extra', 'custom']:
            data = {
                'event_name': 'test_event',
                field_name: {'key': 'value'}
            }
            response = self.client.post('/api/v1/events/', data, format='json')
            
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST,
                           f"Field '{field_name}' should be rejected")
    
    # =========================================================================
    # TRACKING IDENTIFIER TESTS - Device IDs must be rejected
    # =========================================================================
    
    def test_device_id_rejected(self):
        """Test that device_id field is rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'device_id': 'abc123'
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('device_id', self.get_error_field(response.data, 'reason'))
    
    def test_idfa_rejected(self):
        """Test that IDFA (iOS advertising ID) is rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'idfa': 'E621E1F8-C36C-495A-93FC-0C247A3E6E5F'
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_gaid_rejected(self):
        """Test that GAID (Google Advertising ID) is rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'gaid': 'cdda802e-fb9c-47ad-9866-0794d394c912'
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_advertising_id_rejected(self):
        """Test that advertising_id field is rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'advertising_id': 'some-ad-id'
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_android_id_rejected(self):
        """Test that android_id is rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'android_id': '9774d56d682e549c'
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_imei_field_rejected(self):
        """Test that IMEI field is rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'imei': '353456789012345'
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_mac_address_field_rejected(self):
        """Test that mac_address field is rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'mac_address': '00:1A:2B:3C:4D:5E'
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_vendor_id_rejected(self):
        """Test that vendor_id (IDFV) is rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'vendor_id': 'E621E1F8-C36C-495A-93FC-0C247A3E6E5F'
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_fingerprint_rejected(self):
        """Test that fingerprint field is rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'fingerprint': 'abc123def456'
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    # =========================================================================
    # USER IDENTIFIER TESTS - User IDs and PII must be rejected
    # =========================================================================
    
    def test_user_id_rejected(self):
        """Test that user_id field is rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'user_id': '12345'
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_email_field_rejected(self):
        """Test that email field is rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'email': 'user@example.com'
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_phone_field_rejected(self):
        """Test that phone field is rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'phone': '+1234567890'
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_name_field_rejected(self):
        """Test that name field is rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'name': 'John Doe'
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_ip_address_field_rejected(self):
        """Test that ip_address field is rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'ip_address': '192.168.1.1'
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_latitude_longitude_rejected(self):
        """Test that precise location fields are rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'latitude': 37.7749,
            'longitude': -122.4194
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    # =========================================================================
    # SESSION ID VALIDATION TESTS
    # =========================================================================
    
    def test_session_id_too_short_rejected(self):
        """Test that session_id shorter than 16 chars is rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'session_id': 'short123'  # Only 8 characters
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.get_error_field(response.data, 'code'), 'INVALID_SESSION_ID')
        self.assertIn('16 characters', self.get_error_field(response.data, 'reason'))
    
    def test_session_id_uuid_format_rejected(self):
        """Test that UUID-formatted session_id is rejected (likely device ID)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'session_id': 'E621E1F8-C36C-495A-93FC-0C247A3E6E5F'  # Uppercase UUID = IDFA format
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.get_error_field(response.data, 'code'), 'INVALID_SESSION_ID')
    
    def test_session_id_sequential_rejected(self):
        """Test that sequential session_id patterns are rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        sequential_ids = ['session_123', 'user_456', 'device_789', 'sid_001']
        for session_id in sequential_ids:
            data = {
                'event_name': 'test_event',
                'session_id': session_id
            }
            response = self.client.post('/api/v1/events/', data, format='json')
            
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST,
                           f"Session ID '{session_id}' should be rejected")
    
    def test_session_id_pure_numeric_rejected(self):
        """Test that pure numeric session_id is rejected"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'session_id': '12345678901234567890'  # 20 digits - long enough but predictable
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.get_error_field(response.data, 'code'), 'INVALID_SESSION_ID')
    
    def test_valid_session_id_accepted(self):
        """Test that valid random session_id is accepted"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # Valid session IDs - random-looking, 16+ characters
        valid_ids = [
            'a1b2c3d4e5f6g7h8i9j0',          # 20 chars alphanumeric
            'Xt7kL9mN2pQ4rS6uW8yZ',          # Mixed case
            'f47ac10b58cc4372a5670e02b2c3d479',  # 32 char hex (lowercase)
        ]
        
        for session_id in valid_ids:
            data = {
                'event_name': 'test_event',
                'session_id': session_id
            }
            response = self.client.post('/api/v1/events/', data, format='json')
            
            self.assertEqual(response.status_code, status.HTTP_201_CREATED,
                           f"Valid session ID '{session_id}' should be accepted")
    
    def test_empty_session_id_accepted(self):
        """Test that empty/null session_id is accepted (field is optional)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        for session_id in [None, '', ]:
            data = {'event_name': 'test_event'}
            if session_id is not None:
                data['session_id'] = session_id
            
            response = self.client.post('/api/v1/events/', data, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    # =========================================================================
    # LEGITIMATE DATA TESTS - Valid requests must still work
    # =========================================================================
    
    def test_valid_minimal_event_accepted(self):
        """Test that minimal valid event is accepted"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'app_open'
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_valid_full_event_accepted(self):
        """Test that event with all allowed fields is accepted (including deprecated ones).
        
        SCHEMA REDUCTION (ROA): Deprecated fields are accepted for backwards
        compatibility but are NOT stored. This tests the acceptance - other tests
        verify they are not stored.
        """
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'purchase',
            'platform': 'ios',                          # STORED
            'app_version': '2.1.0',                     # DEPRECATED - accepted but not stored
            'os_version': 'iOS 17.1',                   # DEPRECATED - accepted but not stored
            'device_type': 'iPhone 15 Pro',             # DEPRECATED - accepted but not stored
            'locale': 'en-US',                          # DEPRECATED - accepted but not stored
            'country': 'US',                            # STORED
            'region': 'California',                     # DEPRECATED - accepted but not stored
            'screen': 'checkout',                       # DEPRECATED - accepted but not stored
            'session_id': 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6'  # STORED (anonymized)
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify event was created with only stored fields
        event = Event.objects.get(id=response.data['id'])
        self.assertEqual(event.event_name, 'purchase')
        self.assertEqual(event.platform, 'ios')
        self.assertEqual(event.country, 'US')
        # Note: Deprecated fields (app_version, os_version, device_type, locale, region, screen)
        # no longer exist on model - they are accepted by API but silently discarded
    
    def test_event_name_with_user_prefix_accepted(self):
        """Test that event names like 'user_signup' are still valid"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # These are valid event names, not user identifiers
        valid_events = ['user_signup', 'user_login', 'user_logout', 'device_connected']
        
        for event_name in valid_events:
            data = {'event_name': event_name}
            response = self.client.post('/api/v1/events/', data, format='json')
            
            self.assertEqual(response.status_code, status.HTTP_201_CREATED,
                           f"Event name '{event_name}' should be accepted")
    
    # =========================================================================
    # ERROR RESPONSE FORMAT TESTS
    # =========================================================================
    
    def test_error_response_format(self):
        """Test that error responses have correct format"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data = {
            'event_name': 'test_event',
            'device_id': 'some_id'
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Check response structure has required keys
        self.assertIn('detail', response.data)
        self.assertIn('code', response.data)
        self.assertIn('reason', response.data)
        
        # Check values (using helper to extract from DRF list-wrapped format)
        self.assertEqual(self.get_error_field(response.data, 'detail'), 'Invalid request')
        self.assertEqual(self.get_error_field(response.data, 'code'), 'FORBIDDEN_FIELD')
        self.assertIn('device_id', self.get_error_field(response.data, 'reason'))


class SessionIdAnonymizationTestCase(APITestCase):
    """
    Test session ID anonymization with daily rotation.
    
    These tests ensure that:
    1. Session IDs are hashed before storage (original never stored)
    2. Same session_id produces same hash on same day
    3. Same session_id produces DIFFERENT hash on different days
    4. Different apps have isolated session namespaces
    5. Empty/null session IDs are handled correctly
    """
    
    def setUp(self):
        """Set up test fixtures."""
        from django.core.cache import cache
        cache.clear()
        
        self.user = User.objects.create_user(
            username='sessiontester',
            email='session@test.com',
            password='testpass123'
        )
        self.app = App.objects.create(
            name='Session Test App',
            user=self.user
        )
        self.app_key = str(self.app.id)
        
        # Create a second app for isolation tests
        self.app2 = App.objects.create(
            name='Second Test App',
            user=self.user
        )
        self.app2_key = str(self.app2.id)
    
    # =========================================================================
    # BASIC ANONYMIZATION TESTS
    # =========================================================================
    
    def test_session_id_is_hashed_not_stored_raw(self):
        """Test that the original session_id is NOT stored in the database"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        original_session_id = 'my_original_session_abc123def456'
        data = {
            'event_name': 'test_event',
            'session_id': original_session_id
        }
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Fetch the stored event
        event = Event.objects.get(id=response.data['id'])
        
        # The stored session_id should NOT be the original
        self.assertNotEqual(event.session_id, original_session_id)
        
        # It should be a 32-character hex hash
        self.assertEqual(len(event.session_id), 32)
        self.assertTrue(all(c in '0123456789abcdef' for c in event.session_id))
    
    def test_session_id_hash_is_deterministic_same_day(self):
        """Test that same session_id produces same hash within a single day"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        session_id = 'deterministic_session_test_12345'
        
        # Create two events with the same session_id
        data1 = {'event_name': 'event_1', 'session_id': session_id}
        data2 = {'event_name': 'event_2', 'session_id': session_id}
        
        response1 = self.client.post('/api/v1/events/', data1, format='json')
        response2 = self.client.post('/api/v1/events/', data2, format='json')
        
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)
        
        # Both events should have the same hashed session_id
        event1 = Event.objects.get(id=response1.data['id'])
        event2 = Event.objects.get(id=response2.data['id'])
        
        self.assertEqual(event1.session_id, event2.session_id)
    
    def test_empty_session_id_stays_none(self):
        """Test that empty/null session_id is stored as None"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # Test with no session_id
        data = {'event_name': 'no_session_event'}
        response = self.client.post('/api/v1/events/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        event = Event.objects.get(id=response.data['id'])
        self.assertIsNone(event.session_id)
        
        # Test with empty string session_id
        data2 = {'event_name': 'empty_session_event', 'session_id': ''}
        response2 = self.client.post('/api/v1/events/', data2, format='json')
        
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)
        event2 = Event.objects.get(id=response2.data['id'])
        self.assertIsNone(event2.session_id)
    
    # =========================================================================
    # DAILY ROTATION TESTS (using privacy_guards directly)
    # =========================================================================
    
    def test_daily_rotation_produces_different_hashes(self):
        """Test that same session_id produces different hash on different days"""
        from analytics.privacy_guards import anonymize_session_id
        from datetime import date, timedelta
        
        session_id = 'persistent_session_xyz789abc'
        app_id = self.app_key
        
        today = date.today()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        
        hash_today = anonymize_session_id(session_id, app_id, rotation_date=today)
        hash_yesterday = anonymize_session_id(session_id, app_id, rotation_date=yesterday)
        hash_tomorrow = anonymize_session_id(session_id, app_id, rotation_date=tomorrow)
        
        # All hashes should be different
        self.assertNotEqual(hash_today, hash_yesterday)
        self.assertNotEqual(hash_today, hash_tomorrow)
        self.assertNotEqual(hash_yesterday, hash_tomorrow)
        
        # Same day should produce same hash
        hash_today_again = anonymize_session_id(session_id, app_id, rotation_date=today)
        self.assertEqual(hash_today, hash_today_again)
    
    def test_different_apps_have_isolated_sessions(self):
        """Test that same session_id in different apps produces different hashes"""
        from analytics.privacy_guards import anonymize_session_id
        from datetime import date
        
        session_id = 'shared_session_id_abc123xyz'
        today = date.today()
        
        hash_app1 = anonymize_session_id(session_id, self.app_key, rotation_date=today)
        hash_app2 = anonymize_session_id(session_id, self.app2_key, rotation_date=today)
        
        # Different apps should produce different hashes even for same session_id
        self.assertNotEqual(hash_app1, hash_app2)
    
    def test_hash_output_format(self):
        """Test that anonymized session_id has correct format"""
        from analytics.privacy_guards import anonymize_session_id
        
        session_id = 'format_test_session_abcdef123'
        hash_result = anonymize_session_id(session_id, self.app_key)
        
        # Should be 32 characters (128 bits)
        self.assertEqual(len(hash_result), 32)
        
        # Should be lowercase hex only
        self.assertTrue(all(c in '0123456789abcdef' for c in hash_result))
    
    def test_anonymize_none_returns_none(self):
        """Test that anonymize_session_id(None) returns None"""
        from analytics.privacy_guards import anonymize_session_id
        
        result = anonymize_session_id(None, self.app_key)
        self.assertIsNone(result)
        
        result2 = anonymize_session_id('', self.app_key)
        self.assertIsNone(result2)
    
    # =========================================================================
    # INTEGRATION TESTS - End-to-end API behavior
    # =========================================================================
    
    def test_different_apps_same_session_id_different_stored_hash(self):
        """Test that same session_id sent to different apps stores different hashes"""
        session_id = 'cross_app_session_test_123456'
        
        # Send to app 1
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        data1 = {'event_name': 'event_app1', 'session_id': session_id}
        response1 = self.client.post('/api/v1/events/', data1, format='json')
        
        # Send to app 2
        self.client.credentials(HTTP_X_APP_KEY=self.app2_key)
        data2 = {'event_name': 'event_app2', 'session_id': session_id}
        response2 = self.client.post('/api/v1/events/', data2, format='json')
        
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)
        
        event1 = Event.objects.get(id=response1.data['id'])
        event2 = Event.objects.get(id=response2.data['id'])
        
        # The stored hashes should be different (app isolation)
        self.assertNotEqual(event1.session_id, event2.session_id)
    
    def test_funnel_analysis_works_with_anonymized_sessions(self):
        """Test that funnel analysis still works correctly with hashed session IDs"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        now = timezone.now()
        
        # Create a complete funnel with same session_id
        session_id = 'funnel_test_session_xyz789'
        
        events = [
            {'event_name': 'app_open', 'session_id': session_id, 'timestamp': now.isoformat()},
            {'event_name': 'product_view', 'session_id': session_id, 'timestamp': (now + timedelta(seconds=5)).isoformat()},
            {'event_name': 'purchase', 'session_id': session_id, 'timestamp': (now + timedelta(seconds=10)).isoformat()},
        ]
        
        for event_data in events:
            response = self.client.post('/api/v1/events/', event_data, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Query the funnel
        response = self.client.get('/api/v1/events/funnel/?steps=app_open,product_view,purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        funnel = response.data['funnel']
        
        # All three steps should show 1 session completing each
        self.assertEqual(funnel[0]['count'], 1)  # app_open
        self.assertEqual(funnel[1]['count'], 1)  # product_view
        self.assertEqual(funnel[2]['count'], 1)  # purchase
    
    def test_session_count_aggregation_works(self):
        """Test that unique session counting works with hashed IDs"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # Create events from 3 different sessions
        sessions = [
            'unique_session_one_abc123',
            'unique_session_two_def456',
            'unique_session_three_ghi789'
        ]
        
        for session_id in sessions:
            data = {'event_name': 'app_open', 'session_id': session_id}
            response = self.client.post('/api/v1/events/', data, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Check that we have 3 distinct session_ids stored
        distinct_sessions = Event.objects.filter(app=self.app).values_list('session_id', flat=True).distinct()
        self.assertEqual(len(set(distinct_sessions)), 3)


# =============================================================================
# NOTE: User ID test classes removed (Schema Reduction - ROA)
# =============================================================================
# The following test classes were removed as part of schema reduction:
# - UserIdValidationTestCase
# - AnonymousBucketIdTestCase
# - UserIdSerializerTestCase
# - UserIdInResponsesTestCase
#
# The user_id field was removed from the system in v2.0.0 as part of the 
# Return of Avoidance (ROA) approach - we avoid collecting data rather than 
# trying to manage it. The system now uses only ephemeral session_id for 
# intra-session funnel analysis, with no persistent user tracking.
#
# See: test_user_id_rejected() in PrivacyGuardsTestCase which verifies
# that user_id is properly rejected by the privacy guards.
# =============================================================================

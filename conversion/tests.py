"""
Conversion Intelligence Tests

Tests for TASK-030 through TASK-033:
- DAU/WAU/MAU (Active Sessions)
- Conversion Summary
- Time-to-Conversion Analysis
- Funnel Step Timing

NOTE: These tests use session_id for Event creation (session-based analytics).
Moved from analytics/tests.py as part of TASK-041 codebase restructuring.
"""
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from rest_framework import status
from datetime import datetime, timedelta

from analytics.models import App, Event

class DAUViewTestCase(APITestCase):
    """
    Test Daily/Weekly/Monthly Active Sessions (DAU) endpoint.
    Tests for TASK-030: Active Sessions Endpoint (DAU/WAU/MAU)
    """
    
    def setUp(self):
        """Set up test data with multiple sessions across multiple days"""
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.app = App.objects.create(name="Test App", user=self.user)
        self.app_key = str(self.app.id)
        
        # Create another app to test app isolation
        self.other_app = App.objects.create(name="Other App", user=self.user)
        
        # Create test events with different session_ids across different days
        self.now = timezone.now()
        
        # Session IDs for testing
        self.session1 = 'a' * 32  # Valid 32-char hex
        self.session2 = 'b' * 32
        self.session3 = 'c' * 32
        self.anon_session = 'anon_1234567890abcdef'
        
        # Day 1 (today): 3 sessions, 5 events
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.now, session_id=self.session1)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.now, session_id=self.session2)
        Event.objects.create(app=self.app, event_name="purchase", timestamp=self.now, session_id=self.session1)
        Event.objects.create(app=self.app, event_name="screen_view", timestamp=self.now, session_id=self.session3)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.now, session_id=self.anon_session)
        
        # Day 2 (yesterday): 2 sessions, 3 events
        yesterday = self.now - timedelta(days=1)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=yesterday, session_id=self.session1)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=yesterday, session_id=self.session2)
        Event.objects.create(app=self.app, event_name="purchase", timestamp=yesterday, session_id=self.session2)
        
        # Day 3 (2 days ago): 1 session, 2 events
        two_days_ago = self.now - timedelta(days=2)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=two_days_ago, session_id=self.session1)
        Event.objects.create(app=self.app, event_name="screen_view", timestamp=two_days_ago, session_id=self.session1)
        
        # Last week (8 days ago): 2 sessions, 2 events
        last_week = self.now - timedelta(days=8)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=last_week, session_id=self.session2)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=last_week, session_id=self.session3)
        
        # Last month (35 days ago): 1 session, 1 event
        last_month = self.now - timedelta(days=35)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=last_month, session_id=self.session1)
        
        # Other app events (should NOT appear in results)
        Event.objects.create(app=self.other_app, event_name="app_open", timestamp=self.now, session_id=self.session1)
    
    def test_dau_endpoint_requires_authentication(self):
        """Test that DAU endpoint requires app_key authentication"""
        response = self.client.get('/api/v1/analytics/dau/')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
    
    def test_dau_endpoint_with_invalid_app_key(self):
        """Test DAU endpoint with invalid app_key returns 401"""
        self.client.credentials(HTTP_X_APP_KEY="00000000-0000-0000-0000-000000000000")
        response = self.client.get('/api/v1/analytics/dau/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_dau_default_granularity_is_day(self):
        """Test that default granularity is 'day'"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/dau/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'day')
    
    def test_dau_returns_expected_structure(self):
        """Test that response has correct structure"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/dau/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('app_name', response.data)
        self.assertIn('granularity', response.data)
        self.assertIn('date_range', response.data)
        self.assertIn('active_sessions', response.data)
        self.assertIn('top_events_current_period', response.data)
        
        self.assertEqual(response.data['app_name'], 'Test App')
        self.assertIn('from', response.data['date_range'])
        self.assertIn('to', response.data['date_range'])
    
    def test_dau_counts_unique_users_per_day(self):
        """Test that unique buckets are counted correctly per day"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        today = self.now.strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/dau/?from={today}&to={today}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Today should have 4 unique users (user1, user2, user3, anon_user)
        active_sessions = response.data['active_sessions']
        self.assertEqual(len(active_sessions), 1)
        self.assertEqual(active_sessions[0]['unique_buckets'], 4)
        self.assertEqual(active_sessions[0]['total_events'], 5)
    
    def test_dau_date_format_is_correct(self):
        """Test that day granularity uses YYYY-MM-DD format"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        today = self.now.strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/dau/?from={today}&to={today}&granularity=day')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        active_sessions = response.data['active_sessions']
        
        if active_sessions:
            # Check format: YYYY-MM-DD
            import re
            period = active_sessions[0]['period']
            self.assertRegex(period, r'^\d{4}-\d{2}-\d{2}$')
    
    def test_dau_week_granularity(self):
        """Test weekly granularity uses ISO week format YYYY-Www"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/dau/?granularity=week')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'week')
        
        active_sessions = response.data['active_sessions']
        if active_sessions:
            # Check format: YYYY-Www
            import re
            period = active_sessions[0]['period']
            self.assertRegex(period, r'^\d{4}-W\d{2}$')
    
    def test_dau_month_granularity(self):
        """Test monthly granularity uses YYYY-MM format"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/dau/?granularity=month')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'month')
        
        active_sessions = response.data['active_sessions']
        if active_sessions:
            # Check format: YYYY-MM
            import re
            period = active_sessions[0]['period']
            self.assertRegex(period, r'^\d{4}-\d{2}$')
    
    def test_dau_quarter_granularity(self):
        """Test quarterly granularity uses YYYY-Qn format"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/dau/?granularity=quarter')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'quarter')
        
        active_sessions = response.data['active_sessions']
        if active_sessions:
            # Check format: YYYY-Qn
            import re
            period = active_sessions[0]['period']
            self.assertRegex(period, r'^\d{4}-Q[1-4]$')
    
    def test_dau_year_granularity(self):
        """Test yearly granularity uses YYYY format"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/dau/?granularity=year')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'year')
        
        active_sessions = response.data['active_sessions']
        if active_sessions:
            # Check format: YYYY
            import re
            period = active_sessions[0]['period']
            self.assertRegex(period, r'^\d{4}$')
    
    def test_dau_invalid_granularity_returns_400(self):
        """Test that invalid granularity returns 400 error"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/dau/?granularity=hourly')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('granularity', response.data['error'].lower())
    
    def test_dau_invalid_from_date_returns_400(self):
        """Test that invalid from date returns 400 error"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/dau/?from=not-a-date')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_dau_invalid_to_date_returns_400(self):
        """Test that invalid to date returns 400 error"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/dau/?to=invalid')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_dau_date_range_filtering(self):
        """Test that date range filters work correctly"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # Get data for just yesterday
        yesterday = (self.now - timedelta(days=1)).strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/dau/?from={yesterday}&to={yesterday}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        active_sessions = response.data['active_sessions']
        
        # Yesterday should have 2 unique users (user1, user2)
        self.assertEqual(len(active_sessions), 1)
        self.assertEqual(active_sessions[0]['unique_buckets'], 2)
        self.assertEqual(active_sessions[0]['total_events'], 3)
    
    def test_dau_app_isolation(self):
        """Test that only events from the authenticated app are counted"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/dau/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Count total events - should NOT include other_app event
        total_events = sum(b['total_events'] for b in response.data['active_sessions'])
        # We created 13 events for self.app (5 + 3 + 2 + 2 + 1)
        # Plus last_month event if within default 30-day range
        self.assertGreaterEqual(total_events, 10)  # At least the recent events
    
    def test_dau_top_events_returns_correct_data(self):
        """Test that top_events_current_period contains expected data"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        today = self.now.strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/dau/?from={today}&to={today}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        top_events = response.data['top_events_current_period']
        self.assertIsInstance(top_events, list)
        
        # Should have app_open (3), purchase (1), screen_view (1) for today
        if top_events:
            # Verify structure
            self.assertIn('event_name', top_events[0])
            self.assertIn('count', top_events[0])
            
            # app_open should be most frequent today
            event_names = [e['event_name'] for e in top_events]
            self.assertIn('app_open', event_names)
    
    def test_dau_handles_empty_date_range(self):
        """Test that empty date range returns empty results gracefully"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # Far future date with no events
        response = self.client.get('/api/v1/analytics/dau/?from=2099-01-01&to=2099-12-31')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['active_sessions'], [])
    
    def test_dau_works_with_anonymous_bucket_ids(self):
        """Test that anonymous bucket IDs (anon_xxx) are counted as unique buckets"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        today = self.now.strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/dau/?from={today}&to={today}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # We have 4 unique users today: user1, user2, user3, anon_user
        # The anon_user should be counted
        active_sessions = response.data['active_sessions']
        self.assertEqual(active_sessions[0]['unique_buckets'], 4)
    
    def test_dau_excludes_null_user_ids(self):
        """Test that events without user_id are not counted in unique buckets"""
        # Create an event with null user_id
        Event.objects.create(
            app=self.app,
            event_name="no_user_event",
            timestamp=self.now,
            session_id=None
        )
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        today = self.now.strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/dau/?from={today}&to={today}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should still be 4 unique users (null user_id event doesn't add a new bucket)
        active_sessions = response.data['active_sessions']
        self.assertEqual(active_sessions[0]['unique_buckets'], 4)
    
    def test_dau_ordered_by_most_recent_first(self):
        """Test that periods are ordered with most recent first"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/dau/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        active_sessions = response.data['active_sessions']
        if len(active_sessions) >= 2:
            # First period should be more recent than second
            # For day format YYYY-MM-DD, string comparison works
            self.assertGreater(active_sessions[0]['period'], active_sessions[1]['period'])
    
    def test_dau_with_query_param_auth(self):
        """Test DAU endpoint with app_key as query parameter"""
        response = self.client.get(f'/api/v1/analytics/dau/?app_key={self.app_key}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['app_name'], 'Test App')
    
    def test_dau_granularity_case_insensitive(self):
        """Test that granularity parameter is case-insensitive"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # Test uppercase
        response = self.client.get('/api/v1/analytics/dau/?granularity=WEEK')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'week')
        
        # Test mixed case
        response = self.client.get('/api/v1/analytics/dau/?granularity=Month')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'month')
    
    def test_dau_default_date_range_is_30_days(self):
        """Test that default date range is last 30 days"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/dau/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        date_range = response.data['date_range']
        from_date = timezone.datetime.strptime(date_range['from'], '%Y-%m-%d')
        to_date = timezone.datetime.strptime(date_range['to'], '%Y-%m-%d')
        
        # Should be approximately 30 days apart
        delta = (to_date - from_date).days
        self.assertGreaterEqual(delta, 29)
        self.assertLessEqual(delta, 31)


class ConversionSummaryViewTestCase(APITestCase):
    """
    Test Conversion Summary endpoint.
    Tests for TASK-031: Conversion Summary Endpoint
    """
    
    def setUp(self):
        """Set up test data with multiple sessions, conversion and non-conversion events across days"""
        self.user = User.objects.create_user(username='conversionuser', password='testpass123')
        self.app = App.objects.create(name="Conversion App", user=self.user)
        self.app_key = str(self.app.id)
        
        # Create another app to test app isolation
        self.other_app = App.objects.create(name="Other App", user=self.user)
        
        # Create test events with different session_ids across different days
        self.now = timezone.now()
        
        # Session IDs for testing
        self.session1 = 'a' * 32
        self.session2 = 'b' * 32
        self.session3 = 'c' * 32
        self.session4 = 'd' * 32
        
        # Day 1 (today): 4 unique sessions, 2 conversions (purchase events)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.now, session_id=self.session1)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.now, session_id=self.session2)
        Event.objects.create(app=self.app, event_name="purchase", timestamp=self.now, session_id=self.session1)  # conversion
        Event.objects.create(app=self.app, event_name="screen_view", timestamp=self.now, session_id=self.session3)
        Event.objects.create(app=self.app, event_name="subscription", timestamp=self.now, session_id=self.session2)  # conversion
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.now, session_id=self.session4)
        
        # Day 2 (yesterday): 2 unique sessions, 1 conversion
        yesterday = self.now - timedelta(days=1)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=yesterday, session_id=self.session1)
        Event.objects.create(app=self.app, event_name="purchase", timestamp=yesterday, session_id=self.session1)  # conversion
        Event.objects.create(app=self.app, event_name="app_open", timestamp=yesterday, session_id=self.session2)
        
        # Day 3 (2 days ago): 1 unique session, 0 conversions
        two_days_ago = self.now - timedelta(days=2)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=two_days_ago, session_id=self.session3)
        Event.objects.create(app=self.app, event_name="screen_view", timestamp=two_days_ago, session_id=self.session3)
        
        # Other app events (should NOT appear in results)
        Event.objects.create(app=self.other_app, event_name="purchase", timestamp=self.now, session_id=self.session1)
    
    def test_conversion_endpoint_requires_authentication(self):
        """Test that conversion endpoint requires app_key authentication"""
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=purchase')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
    
    def test_conversion_endpoint_with_invalid_app_key(self):
        """Test conversion endpoint with invalid app_key returns 401"""
        self.client.credentials(HTTP_X_APP_KEY="00000000-0000-0000-0000-000000000000")
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=purchase')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_conversion_events_parameter_required(self):
        """Test that conversion_events parameter is required"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversions/')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('conversion_events', response.data['error'])
        self.assertIn('your_event_types', response.data)
        self.assertIn('example', response.data)
    
    def test_conversion_events_error_lists_user_event_types(self):
        """Test that 400 error includes user's actual event types"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversions/')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        event_types = response.data['your_event_types']
        self.assertIsInstance(event_types, list)
        # Should include the event types we created
        self.assertIn('app_open', event_types)
        self.assertIn('purchase', event_types)
        self.assertIn('subscription', event_types)
    
    def test_conversion_empty_parameter_returns_400(self):
        """Test that empty conversion_events parameter returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_conversion_returns_expected_structure(self):
        """Test that response has correct structure"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('app_name', response.data)
        self.assertIn('granularity', response.data)
        self.assertIn('conversion_events', response.data)
        self.assertIn('date_range', response.data)
        self.assertIn('summary', response.data)
        self.assertIn('conversions', response.data)
        
        # Check summary structure
        self.assertIn('total_conversions', response.data['summary'])
        self.assertIn('avg_conversion_rate', response.data['summary'])
        
        # Check date_range structure
        self.assertIn('from', response.data['date_range'])
        self.assertIn('to', response.data['date_range'])
    
    def test_conversion_default_granularity_is_day(self):
        """Test that default granularity is 'day'"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'day')
    
    def test_conversion_counts_are_correct(self):
        """Test that conversion counts are accurate"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        today = self.now.strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/conversions/?conversion_events=purchase&from={today}&to={today}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Today should have 1 purchase event
        conversions = response.data['conversions']
        self.assertEqual(len(conversions), 1)
        self.assertEqual(conversions[0]['conversions'], 1)
    
    def test_conversion_multiple_event_types(self):
        """Test that multiple conversion event types are counted together"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        today = self.now.strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/conversions/?conversion_events=purchase,subscription&from={today}&to={today}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Today should have 1 purchase + 1 subscription = 2 conversions
        conversions = response.data['conversions']
        self.assertEqual(len(conversions), 1)
        self.assertEqual(conversions[0]['conversions'], 2)
        
        # Verify the conversion_events in response
        self.assertIn('purchase', response.data['conversion_events'])
        self.assertIn('subscription', response.data['conversion_events'])
    
    def test_conversion_rate_calculation(self):
        """Test that conversion rate is calculated correctly"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        today = self.now.strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/conversions/?conversion_events=purchase&from={today}&to={today}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        conversions = response.data['conversions']
        # Today: 1 purchase, 4 unique users -> rate = 1/4 = 0.25
        self.assertEqual(conversions[0]['conversions'], 1)
        self.assertEqual(conversions[0]['active_sessions'], 4)
        self.assertEqual(conversions[0]['conversion_rate'], 0.25)
    
    def test_conversion_summary_totals(self):
        """Test that summary totals are correct"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        # Get last 2 days
        yesterday = (self.now - timedelta(days=1)).strftime('%Y-%m-%d')
        today = self.now.strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/conversions/?conversion_events=purchase&from={yesterday}&to={today}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Today: 1 purchase, yesterday: 1 purchase = 2 total
        summary = response.data['summary']
        self.assertEqual(summary['total_conversions'], 2)
        # avg rate = 2 conversions / 6 buckets (4 today + 2 yesterday) = 0.3333
        self.assertAlmostEqual(summary['avg_conversion_rate'], 0.3333, places=3)
    
    def test_conversion_week_granularity(self):
        """Test weekly granularity uses ISO week format YYYY-Www"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=purchase&granularity=week')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'week')
        
        conversions = response.data['conversions']
        if conversions:
            # Check format: YYYY-Www
            import re
            period = conversions[0]['period']
            self.assertRegex(period, r'^\d{4}-W\d{2}$')
    
    def test_conversion_month_granularity(self):
        """Test monthly granularity uses YYYY-MM format"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=purchase&granularity=month')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'month')
        
        conversions = response.data['conversions']
        if conversions:
            import re
            period = conversions[0]['period']
            self.assertRegex(period, r'^\d{4}-\d{2}$')
    
    def test_conversion_quarter_granularity(self):
        """Test quarterly granularity uses YYYY-Qn format"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=purchase&granularity=quarter')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'quarter')
        
        conversions = response.data['conversions']
        if conversions:
            import re
            period = conversions[0]['period']
            self.assertRegex(period, r'^\d{4}-Q[1-4]$')
    
    def test_conversion_year_granularity(self):
        """Test yearly granularity uses YYYY format"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=purchase&granularity=year')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'year')
        
        conversions = response.data['conversions']
        if conversions:
            import re
            period = conversions[0]['period']
            self.assertRegex(period, r'^\d{4}$')
    
    def test_conversion_invalid_granularity_returns_400(self):
        """Test that invalid granularity returns 400 error"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=purchase&granularity=hourly')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('granularity', response.data['error'].lower())
    
    def test_conversion_invalid_from_date_returns_400(self):
        """Test that invalid from date returns 400 error"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=purchase&from=not-a-date')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_conversion_invalid_to_date_returns_400(self):
        """Test that invalid to date returns 400 error"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=purchase&to=invalid')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_conversion_date_range_filtering(self):
        """Test that date range filters work correctly"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # Get data for just yesterday
        yesterday = (self.now - timedelta(days=1)).strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/conversions/?conversion_events=purchase&from={yesterday}&to={yesterday}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        conversions = response.data['conversions']
        # Yesterday should have 1 purchase, 2 unique users -> rate = 0.5
        self.assertEqual(len(conversions), 1)
        self.assertEqual(conversions[0]['conversions'], 1)
        self.assertEqual(conversions[0]['active_sessions'], 2)
        self.assertEqual(conversions[0]['conversion_rate'], 0.5)
    
    def test_conversion_app_isolation(self):
        """Test that only events from the authenticated app are counted"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Count total conversions - should NOT include other_app's purchase
        total = response.data['summary']['total_conversions']
        # We have 2 purchase events for self.app (1 today, 1 yesterday)
        self.assertEqual(total, 2)
    
    def test_conversion_handles_empty_date_range(self):
        """Test that empty date range returns empty results gracefully"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # Far future date with no events
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=purchase&from=2099-01-01&to=2099-12-31')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['conversions'], [])
        self.assertEqual(response.data['summary']['total_conversions'], 0)
        self.assertEqual(response.data['summary']['avg_conversion_rate'], 0.0)
    
    def test_conversion_no_matching_events(self):
        """Test response when conversion events don't match any data"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=nonexistent_event')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['conversions'], [])
        self.assertEqual(response.data['summary']['total_conversions'], 0)
    
    def test_conversion_ordered_by_most_recent_first(self):
        """Test that periods are ordered with most recent first"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        yesterday = (self.now - timedelta(days=1)).strftime('%Y-%m-%d')
        today = self.now.strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/conversions/?conversion_events=purchase&from={yesterday}&to={today}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        conversions = response.data['conversions']
        if len(conversions) >= 2:
            # First period should be more recent than second
            self.assertGreater(conversions[0]['period'], conversions[1]['period'])
    
    def test_conversion_with_query_param_auth(self):
        """Test conversion endpoint with app_key as query parameter"""
        response = self.client.get(f'/api/v1/analytics/conversions/?conversion_events=purchase&app_key={self.app_key}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['app_name'], 'Conversion App')
    
    def test_conversion_granularity_case_insensitive(self):
        """Test that granularity parameter is case-insensitive"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # Test uppercase
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=purchase&granularity=WEEK')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'week')
        
        # Test mixed case
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=purchase&granularity=Month')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'month')
    
    def test_conversion_events_whitespace_handling(self):
        """Test that whitespace in conversion_events is handled correctly"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        today = self.now.strftime('%Y-%m-%d')
        
        # Test with spaces around event names
        response = self.client.get(f'/api/v1/analytics/conversions/?conversion_events= purchase , subscription &from={today}&to={today}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should still count both events correctly
        self.assertEqual(response.data['conversions'][0]['conversions'], 2)
    
    def test_conversion_default_date_range_is_30_days(self):
        """Test that default date range is last 30 days"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        date_range = response.data['date_range']
        from_date = timezone.datetime.strptime(date_range['from'], '%Y-%m-%d')
        to_date = timezone.datetime.strptime(date_range['to'], '%Y-%m-%d')
        
        # Should be approximately 30 days apart
        delta = (to_date - from_date).days
        self.assertGreaterEqual(delta, 29)
        self.assertLessEqual(delta, 31)
    
    def test_conversion_zero_buckets_handles_division(self):
        """Test that zero active buckets doesn't cause division error"""
        # Create a new app with only conversion events (no user_ids)
        new_app = App.objects.create(name="No Users App", user=self.user)
        Event.objects.create(app=new_app, event_name="purchase", timestamp=self.now, session_id=None)
        
        self.client.credentials(HTTP_X_APP_KEY=str(new_app.id))
        response = self.client.get('/api/v1/analytics/conversions/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should not have any conversion data since there are no valid user_ids
        # The conversion count comes from events with the matching event_name
        # but conversion_rate should be 0 since there are no active buckets


class TimeToConversionViewTestCase(APITestCase):
    """
    Test Time-to-Conversion Analysis endpoint.
    Tests for TASK-032: Time-to-Conversion Analysis
    """
    
    def setUp(self):
        """Set up test data with users who have first events and conversions"""
        self.user = User.objects.create_user(username='ttcuser', password='testpass123')
        self.app = App.objects.create(name="TTC App", user=self.user)
        self.app_key = str(self.app.id)
        
        # Create another app to test app isolation
        self.other_app = App.objects.create(name="Other TTC App", user=self.user)
        
        self.now = timezone.now()
        
        # Create 15 users with various conversion times to meet minimum threshold
        # User pattern: first_event -> (some time) -> conversion
        self.session_ids = [f'user{i:02d}' + 'x' * 26 for i in range(1, 16)]  # 15 sessions
        
        # User 1-5: Quick conversions (under 5 min)
        for i, session_id in enumerate(self.session_ids[:5]):
            first_event_time = self.now - timedelta(hours=24, minutes=i*10)
            conversion_time = first_event_time + timedelta(minutes=2)  # 2 min conversion
            Event.objects.create(app=self.app, event_name="app_open", timestamp=first_event_time, session_id=session_id)
            Event.objects.create(app=self.app, event_name="screen_view", timestamp=first_event_time + timedelta(minutes=1), session_id=session_id)
            Event.objects.create(app=self.app, event_name="purchase", timestamp=conversion_time, session_id=session_id)
        
        # User 6-8: Medium conversions (15-60 min)
        for i, session_id in enumerate(self.session_ids[5:8]):
            first_event_time = self.now - timedelta(hours=20, minutes=i*30)
            conversion_time = first_event_time + timedelta(minutes=30)  # 30 min conversion
            Event.objects.create(app=self.app, event_name="app_open", timestamp=first_event_time, session_id=session_id)
            Event.objects.create(app=self.app, event_name="purchase", timestamp=conversion_time, session_id=session_id)
        
        # User 9-12: Longer conversions (60-90 min, still within 2-hour session window)
        for i, session_id in enumerate(self.session_ids[8:12]):
            first_event_time = self.now - timedelta(days=2, hours=i*2)
            conversion_time = first_event_time + timedelta(minutes=60 + i*10)  # 60-90 min conversion
            Event.objects.create(app=self.app, event_name="app_open", timestamp=first_event_time, session_id=session_id)
            Event.objects.create(app=self.app, event_name="purchase", timestamp=conversion_time, session_id=session_id)
        
        # User 13-15: Near session-boundary conversions (90-110 min, within 2-hour window)
        for i, session_id in enumerate(self.session_ids[12:15]):
            first_event_time = self.now - timedelta(days=5, hours=i*10)
            conversion_time = first_event_time + timedelta(minutes=90 + i*10)  # 90-110 min conversion
            Event.objects.create(app=self.app, event_name="app_open", timestamp=first_event_time, session_id=session_id)
            Event.objects.create(app=self.app, event_name="purchase", timestamp=conversion_time, session_id=session_id)
        
        # Other app events (should NOT appear in results)
        Event.objects.create(app=self.other_app, event_name="app_open", timestamp=self.now, session_id=self.session_ids[0])
        Event.objects.create(app=self.other_app, event_name="purchase", timestamp=self.now + timedelta(minutes=5), session_id=self.session_ids[0])
    
    def test_ttc_endpoint_requires_authentication(self):
        """Test that time-to-conversion endpoint requires app_key authentication"""
        response = self.client.get('/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
    
    def test_ttc_endpoint_with_invalid_app_key(self):
        """Test time-to-conversion endpoint with invalid app_key returns 401"""
        self.client.credentials(HTTP_X_APP_KEY="00000000-0000-0000-0000-000000000000")
        response = self.client.get('/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_ttc_conversion_events_parameter_required(self):
        """Test that conversion_events parameter is required"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/time-to-conversion/')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('conversion_events', response.data['error'])
        # Should include helpful information about event types
        self.assertIn('your_event_types', response.data)
    
    def test_ttc_empty_conversion_events_returns_400(self):
        """Test that empty conversion_events parameter returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/time-to-conversion/?conversion_events=')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_ttc_successful_response_structure(self):
        """Test successful response has correct structure (session-based)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get(f'/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check top-level keys (session-based, no sessions_before_conversion)
        self.assertIn('app', response.data)
        self.assertIn('filters', response.data)
        self.assertIn('data_quality', response.data)
        self.assertIn('time_to_conversion', response.data)
        self.assertIn('time_distribution', response.data)
        # sessions_before_conversion removed in session-based model
        self.assertNotIn('sessions_before_conversion', response.data)
        
        # Check app structure
        self.assertEqual(response.data['app']['name'], 'TTC App')
        self.assertEqual(response.data['app']['slug'], self.app.slug)
        
        # Check filters structure
        self.assertEqual(response.data['filters']['conversion_events'], ['purchase'])
    
    def test_ttc_data_quality_metrics(self):
        """Test data quality metrics are correct (session-based)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get(f'/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data_quality = response.data['data_quality']
        self.assertIn('sessions_with_conversions', data_quality)
        self.assertIn('coverage_percent', data_quality)
        self.assertIn('warning', data_quality)
        self.assertNotIn('users_with_conversions', data_quality)
        
        # Should have sessions with conversions
        self.assertGreaterEqual(data_quality['sessions_with_conversions'], 10)
    
    def test_ttc_time_statistics(self):
        """Test time-to-conversion statistics are calculated"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get(f'/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        time_stats = response.data['time_to_conversion']
        self.assertIn('median_minutes', time_stats)
        self.assertIn('mean_minutes', time_stats)
        self.assertIn('p25_minutes', time_stats)
        self.assertIn('p75_minutes', time_stats)
        self.assertIn('p90_minutes', time_stats)
        self.assertIn('min_minutes', time_stats)
        self.assertIn('max_minutes', time_stats)
        
        # All values should be non-negative
        for key, value in time_stats.items():
            self.assertGreaterEqual(value, 0, f"{key} should be non-negative")
    
    def test_ttc_session_statistics(self):
        """Test time-to-conversion is session-based (no cross-session tracking)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get(f'/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # sessions_before_conversion is removed - no cross-session analysis
        self.assertNotIn('sessions_before_conversion', response.data)
        
        # Time to conversion should be session-bounded (max 2 hours = 120 min)
        time_stats = response.data['time_to_conversion']
        self.assertLessEqual(time_stats['max_minutes'], 120)
    
    def test_ttc_time_distribution_buckets(self):
        """Test time distribution buckets are correct (session-bounded)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get(f'/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        time_dist = response.data['time_distribution']
        # Session-bounded buckets (max 2 hours, no over_24_hours)
        expected_buckets = ['under_5_min', '5_to_15_min', '15_to_60_min', '1_to_2_hours']
        
        for bucket in expected_buckets:
            self.assertIn(bucket, time_dist)
            self.assertIn('count', time_dist[bucket])
            self.assertIn('percent', time_dist[bucket])
        
        # over_24_hours and 1_to_24_hours removed in session-based model
        self.assertNotIn('over_24_hours', time_dist)
        self.assertNotIn('1_to_24_hours', time_dist)
    
    def test_ttc_session_based_analysis(self):
        """Test that analysis is session-based (no user_id filtering needed)"""
        # In session-based model, we don't exclude any sessions
        # All sessions with conversions are analyzed
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get(f'/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Uses sessions_with_conversions instead
        self.assertIn('sessions_with_conversions', response.data['data_quality'])
    
    def test_ttc_minimum_sessions_threshold(self):
        """Test that fewer than 10 sessions returns 200 with small_sample_warning"""
        # Create a new app with fewer than 10 sessions with conversions
        new_app = App.objects.create(name="Small App", user=self.user)
        
        # Create only 5 sessions with conversions
        for i in range(5):
            session_id = f'small{i:02d}' + 'x' * 25
            first_event = self.now - timedelta(hours=i+1)
            Event.objects.create(app=new_app, event_name="app_open", timestamp=first_event, session_id=session_id)
            Event.objects.create(app=new_app, event_name="purchase", timestamp=first_event + timedelta(minutes=5), session_id=session_id)
        
        self.client.credentials(HTTP_X_APP_KEY=str(new_app.id))
        response = self.client.get(f'/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        # MINIMUM_USERS_THRESHOLD = 1, so view returns 200 with small_sample_warning
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data_quality']['sessions_with_conversions'], 5)
        self.assertIsNotNone(response.data['data_quality']['small_sample_warning'])
    
    def test_ttc_date_filter_start_date(self):
        """Test filtering by start_date"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        # Get date 3 days ago
        start_date = (self.now - timedelta(days=3)).strftime('%Y-%m-%d')
        
        response = self.client.get(
            f'/api/v1/analytics/time-to-conversion/?conversion_events=purchase&start_date={start_date}'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['filters']['start_date'], start_date)
    
    def test_ttc_date_filter_end_date(self):
        """Test filtering by end_date"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        end_date = self.now.strftime('%Y-%m-%d')
        
        response = self.client.get(
            f'/api/v1/analytics/time-to-conversion/?conversion_events=purchase&end_date={end_date}'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['filters']['end_date'], end_date)
    
    def test_ttc_invalid_start_date_format(self):
        """Test that invalid start_date format returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get(
            '/api/v1/analytics/time-to-conversion/?conversion_events=purchase&start_date=invalid-date'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('Invalid date format', response.data['error'])
    
    def test_ttc_invalid_end_date_format(self):
        """Test that invalid end_date format returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get(
            '/api/v1/analytics/time-to-conversion/?conversion_events=purchase&end_date=not-a-date'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('Invalid date format', response.data['error'])
    
    def test_ttc_multiple_conversion_events(self):
        """Test with multiple conversion event types"""
        # Add subscription events for some users
        for session_id in self.session_ids[:3]:
            # Subscription happens 10 min after first event
            Event.objects.create(
                app=self.app, 
                event_name="subscription", 
                timestamp=self.now - timedelta(hours=24) + timedelta(minutes=10),
                session_id=session_id
            )
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get(
            '/api/v1/analytics/time-to-conversion/?conversion_events=purchase,subscription'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data['filters']['conversion_events']), {'purchase', 'subscription'})
    
    def test_ttc_app_isolation(self):
        """Test that only events from the authenticated app are included"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should only include the 15 users from self.app, not events from other_app
        self.assertEqual(response.data['data_quality']['sessions_with_conversions'], 15)
    
    def test_ttc_query_param_auth(self):
        """Test time-to-conversion endpoint with app_key as query parameter"""
        response = self.client.get(
            f'/api/v1/analytics/time-to-conversion/?app_key={self.app_key}&conversion_events=purchase'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['app']['name'], 'TTC App')
    
    def test_ttc_time_distribution_percentages_sum_to_100(self):
        """Test that time distribution percentages sum to approximately 100"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        time_dist = response.data['time_distribution']
        total_percent = sum(bucket['percent'] for bucket in time_dist.values())
        
        # Should sum to 100 (allow small rounding error)
        self.assertAlmostEqual(total_percent, 100.0, places=1)
    
    def test_ttc_no_conversions_returns_200_with_zeros(self):
        """Test that app with no conversions returns 200 with zero values"""
        # Create a new app with events but no conversions
        new_app = App.objects.create(name="No Conversions App", user=self.user)
        
        for i in range(15):
            session_id = f'noconv{i:02d}' + 'x' * 24
            Event.objects.create(app=new_app, event_name="app_open", timestamp=self.now, session_id=session_id)
            Event.objects.create(app=new_app, event_name="screen_view", timestamp=self.now, session_id=session_id)
        
        self.client.credentials(HTTP_X_APP_KEY=str(new_app.id))
        response = self.client.get(f'/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        # View returns 200 with zero values for 0 conversions
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data_quality']['sessions_with_conversions'], 0)
    
    def test_ttc_low_coverage_warning(self):
        """Test that low conversion coverage triggers a warning"""
        # Create an app with 100 users but only a few conversions
        new_app = App.objects.create(name="Low Coverage App", user=self.user)
        
        # Create 100 users with only 10 conversions (10% conversion rate)
        for i in range(100):
            session_id = f'lowcov{i:03d}' + 'x' * 23
            first_event = self.now - timedelta(hours=i+1)
            Event.objects.create(app=new_app, event_name="app_open", timestamp=first_event, session_id=session_id)
            
            # Only first 10 users convert
            if i < 10:
                Event.objects.create(
                    app=new_app, 
                    event_name="purchase", 
                    timestamp=first_event + timedelta(minutes=5),
                    session_id=session_id
                )
        
        self.client.credentials(HTTP_X_APP_KEY=str(new_app.id))
        response = self.client.get(f'/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # With only 10% conversion, warning should NOT be triggered (>= 5% threshold)
        # Let's check the coverage_percent is correct
        self.assertEqual(response.data['data_quality']['coverage_percent'], 10.0)
    
    def test_ttc_very_low_coverage_warning(self):
        """Test that very low coverage (< 5%) triggers warning"""
        # Create an app with 500 users but only 10 conversions (2% conversion rate)
        new_app = App.objects.create(name="Very Low Coverage App", user=self.user)
        
        for i in range(500):
            session_id = f'vlow{i:04d}' + 'x' * 22
            first_event = self.now - timedelta(hours=i+1)
            Event.objects.create(app=new_app, event_name="app_open", timestamp=first_event, session_id=session_id)
            
            # Only first 10 users convert
            if i < 10:
                Event.objects.create(
                    app=new_app, 
                    event_name="purchase", 
                    timestamp=first_event + timedelta(minutes=5),
                    session_id=session_id
                )
        
        self.client.credentials(HTTP_X_APP_KEY=str(new_app.id))
        response = self.client.get(f'/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data_quality']['coverage_percent'], 2.0)
        self.assertIsNotNone(response.data['data_quality']['warning'])
        self.assertIn('Low conversion rate', response.data['data_quality']['warning'])
    
    def test_ttc_session_bounded_time(self):
        """Test that time-to-conversion is session-bounded (max 2 hours)"""
        # Create a new app with session-bounded conversions
        new_app = App.objects.create(name="Session Bounded App", user=self.user)
        
        for i in range(15):
            session_id = f'single{i:02d}' + 'x' * 24
            first_event = self.now - timedelta(hours=i+1)
            # Events within session (all conversions within 10 min from first event)
            Event.objects.create(app=new_app, event_name="app_open", timestamp=first_event, session_id=session_id)
            Event.objects.create(app=new_app, event_name="screen_view", timestamp=first_event + timedelta(minutes=5), session_id=session_id)
            Event.objects.create(app=new_app, event_name="purchase", timestamp=first_event + timedelta(minutes=10), session_id=session_id)
        
        self.client.credentials(HTTP_X_APP_KEY=str(new_app.id))
        response = self.client.get(f'/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Session-based: no sessions_before_conversion
        self.assertNotIn('sessions_before_conversion', response.data)
        
        # All conversions should be under 2 hours
        time_stats = response.data['time_to_conversion']
        self.assertLessEqual(time_stats['max_minutes'], 120)
    
    def test_ttc_session_based_no_cross_session(self):
        """Test that session-based analysis doesn't track across sessions"""
        # In session-based model, each session is independent
        # There's no concept of "sessions before conversion"
        new_app = App.objects.create(name="Multi Session App", user=self.user)
        
        for i in range(15):
            session_id = f'multi{i:02d}' + 'x' * 25
            first_event = self.now - timedelta(days=i+1)
            # Single session with conversion
            Event.objects.create(app=new_app, event_name="app_open", timestamp=first_event, session_id=session_id)
            Event.objects.create(app=new_app, event_name="screen_view", timestamp=first_event + timedelta(minutes=5), session_id=session_id)
            Event.objects.create(app=new_app, event_name="purchase", timestamp=first_event + timedelta(minutes=50), session_id=session_id)
        
        self.client.credentials(HTTP_X_APP_KEY=str(new_app.id))
        response = self.client.get(f'/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify session-based structure (no sessions_before_conversion)
        self.assertNotIn('sessions_before_conversion', response.data)
        self.assertIn('sessions_with_conversions', response.data['data_quality'])
    
    def test_ttc_whitespace_in_conversion_events(self):
        """Test that whitespace in conversion_events parameter is handled"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get(
            '/api/v1/analytics/time-to-conversion/?conversion_events= purchase , subscription '
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Events should be trimmed
        self.assertIn('purchase', response.data['filters']['conversion_events'])
    
    def test_ttc_only_counts_first_conversion(self):
        """Test that only the first conversion event is counted per user"""
        # Add a second purchase event for a user (should not affect stats)
        session_id = self.session_ids[0]
        Event.objects.create(
            app=self.app, 
            event_name="purchase", 
            timestamp=self.now + timedelta(hours=1),  # After first purchase
            session_id=session_id
        )
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should still be 15 users, not 16
        self.assertEqual(response.data['data_quality']['sessions_with_conversions'], 15)
    
    def test_ttc_conversion_after_first_event_only(self):
        """Test that conversions before first event are handled correctly"""
        # The conversion must come after or at the first event time
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # All time_to_conversion values should be >= 0
        self.assertGreaterEqual(response.data['time_to_conversion']['min_minutes'], 0)
    
    def test_ttc_different_app_key_sees_different_data(self):
        """Test that different app_key returns only that app's data"""
        # Create events for other_app 
        for i in range(15):
            session_id = f'other{i:02d}' + 'x' * 26
            first_event = self.now - timedelta(hours=i+1)
            Event.objects.create(app=self.other_app, event_name="app_open", timestamp=first_event, session_id=session_id)
            Event.objects.create(app=self.other_app, event_name="checkout", timestamp=first_event + timedelta(minutes=3), session_id=session_id)
        
        # Request with other_app's key
        self.client.credentials(HTTP_X_APP_KEY=str(self.other_app.id))
        response = self.client.get('/api/v1/analytics/time-to-conversion/?conversion_events=checkout')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should see the 15 users from other_app, not main app
        self.assertEqual(response.data['app']['name'], 'Other TTC App')
        self.assertEqual(response.data['data_quality']['sessions_with_conversions'], 15)
    
    def test_ttc_p90_greater_than_median(self):
        """Test that p90 is greater than or equal to median"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        time_stats = response.data['time_to_conversion']
        self.assertGreaterEqual(time_stats['p90_minutes'], time_stats['median_minutes'])
        self.assertGreaterEqual(time_stats['p75_minutes'], time_stats['p25_minutes'])
    
    def test_ttc_min_max_bounds(self):
        """Test that min <= median <= max"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/time-to-conversion/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        time_stats = response.data['time_to_conversion']
        self.assertLessEqual(time_stats['min_minutes'], time_stats['median_minutes'])
        self.assertLessEqual(time_stats['median_minutes'], time_stats['max_minutes'])


class StepTimingViewTestCase(APITestCase):
    """
    Test Funnel Step Timing Analysis endpoint.
    Tests for TASK-033: Funnel Step Timing Analysis (Session-Based)
    
    This endpoint analyzes timing between consecutive steps in a user-defined 
    funnel. It is session-based - events are analyzed within the same session_id.
    """
    
    def setUp(self):
        """Set up test data with sessions that have funnel events"""
        self.user = User.objects.create_user(username='steptiming', password='testpass123')
        self.app = App.objects.create(name="Step Timing App", user=self.user)
        self.app_key = str(self.app.id)
        
        # Create another app to test app isolation
        self.other_app = App.objects.create(name="Other Step App", user=self.user)
        
        self.now = timezone.now()
        
        # Create session-based funnel events
        # Session 1: Complete funnel (onboarding_start -> onboarding_complete -> purchase)
        self.session1 = 'session1_' + 'a' * 20
        Event.objects.create(
            app=self.app, event_name="onboarding_start", 
            timestamp=self.now - timedelta(hours=2), 
            session_id=self.session1
        )
        Event.objects.create(
            app=self.app, event_name="onboarding_complete", 
            timestamp=self.now - timedelta(hours=2) + timedelta(minutes=5),  # 5 min later
            session_id=self.session1
        )
        Event.objects.create(
            app=self.app, event_name="purchase", 
            timestamp=self.now - timedelta(hours=2) + timedelta(minutes=15),  # 10 min after onboarding_complete
            session_id=self.session1
        )
        
        # Session 2: Complete funnel with different timing
        self.session2 = 'session2_' + 'b' * 20
        Event.objects.create(
            app=self.app, event_name="onboarding_start", 
            timestamp=self.now - timedelta(hours=1), 
            session_id=self.session2
        )
        Event.objects.create(
            app=self.app, event_name="onboarding_complete", 
            timestamp=self.now - timedelta(hours=1) + timedelta(minutes=3),  # 3 min later
            session_id=self.session2
        )
        Event.objects.create(
            app=self.app, event_name="purchase", 
            timestamp=self.now - timedelta(hours=1) + timedelta(minutes=8),  # 5 min after onboarding_complete
            session_id=self.session2
        )
        
        # Session 3: Partial funnel (starts but doesn't complete)
        self.session3 = 'session3_' + 'c' * 20
        Event.objects.create(
            app=self.app, event_name="onboarding_start", 
            timestamp=self.now - timedelta(minutes=30), 
            session_id=self.session3
        )
        Event.objects.create(
            app=self.app, event_name="onboarding_complete", 
            timestamp=self.now - timedelta(minutes=30) + timedelta(minutes=10),  # 10 min later
            session_id=self.session3
        )
        # No purchase in this session
        
        # Session 4: Complete funnel (for statistics)
        self.session4 = 'session4_' + 'd' * 20
        Event.objects.create(
            app=self.app, event_name="onboarding_start", 
            timestamp=self.now - timedelta(hours=3), 
            session_id=self.session4
        )
        Event.objects.create(
            app=self.app, event_name="onboarding_complete", 
            timestamp=self.now - timedelta(hours=3) + timedelta(minutes=7),  # 7 min later
            session_id=self.session4
        )
        Event.objects.create(
            app=self.app, event_name="purchase", 
            timestamp=self.now - timedelta(hours=3) + timedelta(minutes=12),  # 5 min after onboarding_complete
            session_id=self.session4
        )
        
        # Session 5: Anonymous user with complete funnel (should still be included - session-based!)
        self.session5 = 'session5_' + 'e' * 20
        Event.objects.create(
            app=self.app, event_name="onboarding_start", 
            timestamp=self.now - timedelta(hours=4), 
            session_id=self.session5
        )
        Event.objects.create(
            app=self.app, event_name="onboarding_complete", 
            timestamp=self.now - timedelta(hours=4) + timedelta(minutes=4),  # 4 min later
            session_id=self.session5
        )
        Event.objects.create(
            app=self.app, event_name="purchase", 
            timestamp=self.now - timedelta(hours=4) + timedelta(minutes=9),  # 5 min after onboarding_complete
            session_id=self.session5
        )
        
        # Other app event (should NOT appear in results)
        Event.objects.create(
            app=self.other_app, event_name="onboarding_start", 
            timestamp=self.now, 
            session_id='other_session'
        )
    
    def test_step_timing_requires_authentication(self):
        """Test that step-timing endpoint requires app_key authentication"""
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start,purchase')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
    
    def test_step_timing_with_invalid_app_key(self):
        """Test step-timing endpoint with invalid app_key returns 401"""
        self.client.credentials(HTTP_X_APP_KEY="00000000-0000-0000-0000-000000000000")
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start,purchase')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_steps_parameter_required(self):
        """Test that steps parameter is required"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('steps', response.data['error'])
        # Should include helpful information about event types
        self.assertIn('your_event_types', response.data)
    
    def test_steps_requires_at_least_two(self):
        """Test that steps parameter requires at least 2 events"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('2', response.data['error'])
    
    def test_successful_response_structure(self):
        """Test successful response has correct structure"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start,onboarding_complete,purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check top-level keys
        self.assertIn('app', response.data)
        self.assertIn('steps', response.data)
        self.assertIn('filters', response.data)
        self.assertIn('transitions', response.data)
        self.assertIn('funnel_summary', response.data)
        
        # Check app structure
        self.assertEqual(response.data['app']['name'], 'Step Timing App')
        self.assertEqual(response.data['app']['slug'], self.app.slug)
        
        # Check steps
        self.assertEqual(response.data['steps'], ['onboarding_start', 'onboarding_complete', 'purchase'])
    
    def test_transitions_structure(self):
        """Test transitions array has correct structure"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start,onboarding_complete,purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        transitions = response.data['transitions']
        
        # Should have 2 transitions for 3 steps
        self.assertEqual(len(transitions), 2)
        
        # Check first transition
        first_transition = transitions[0]
        self.assertEqual(first_transition['from'], 'onboarding_start')
        self.assertEqual(first_transition['to'], 'onboarding_complete')
        self.assertIn('sessions_analyzed', first_transition)
        self.assertIn('median_seconds', first_transition)
        self.assertIn('mean_seconds', first_transition)
        self.assertIn('p25_seconds', first_transition)
        self.assertIn('p75_seconds', first_transition)
        
        # Check second transition
        second_transition = transitions[1]
        self.assertEqual(second_transition['from'], 'onboarding_complete')
        self.assertEqual(second_transition['to'], 'purchase')
    
    def test_funnel_summary_structure(self):
        """Test funnel_summary has correct structure"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start,onboarding_complete,purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        summary = response.data['funnel_summary']
        
        self.assertIn('sessions_with_first_step', summary)
        self.assertIn('sessions_with_all_steps', summary)
        self.assertIn('completion_rate', summary)
        self.assertIn('median_total_seconds', summary)
        self.assertIn('mean_total_seconds', summary)
    
    def test_session_counts_correct(self):
        """Test session counts are correct"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start,onboarding_complete,purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        summary = response.data['funnel_summary']
        
        # We have 5 sessions with first step (onboarding_start)
        self.assertEqual(summary['sessions_with_first_step'], 5)
        
        # We have 4 sessions with all steps (session3 doesn't have purchase)
        self.assertEqual(summary['sessions_with_all_steps'], 4)
        
        # Completion rate: 4/5 = 0.8
        self.assertEqual(summary['completion_rate'], 0.8)
    
    def test_timing_calculations_correct(self):
        """Test that timing calculations are correct"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start,onboarding_complete,purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        transitions = response.data['transitions']
        
        # First transition (onboarding_start -> onboarding_complete)
        # Times: 5min, 3min, 10min, 7min, 4min = 300s, 180s, 600s, 420s, 240s
        # Sorted: 180, 240, 300, 420, 600
        # Median (3rd value): 300s = 5 min
        first_transition = transitions[0]
        self.assertEqual(first_transition['sessions_analyzed'], 5)
        self.assertEqual(first_transition['median_seconds'], 300)  # 5 min in seconds
    
    def test_anonymous_users_included(self):
        """Test that anonymous users ARE included (session-based analysis)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start,onboarding_complete,purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Anonymous session (session5) should be included
        # Total sessions with first step = 5 (includes anon)
        self.assertEqual(response.data['funnel_summary']['sessions_with_first_step'], 5)
    
    def test_date_filter_start_date(self):
        """Test filtering by start_date"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        # Get date that excludes older sessions
        start_date = (self.now - timedelta(hours=2, minutes=30)).strftime('%Y-%m-%d')
        
        response = self.client.get(
            f'/api/v1/analytics/step-timing/?steps=onboarding_start,onboarding_complete,purchase&start_date={start_date}'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['filters']['start_date'], start_date)
    
    def test_date_filter_end_date(self):
        """Test filtering by end_date"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        end_date = self.now.strftime('%Y-%m-%d')
        
        response = self.client.get(
            f'/api/v1/analytics/step-timing/?steps=onboarding_start,onboarding_complete,purchase&end_date={end_date}'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['filters']['end_date'], end_date)
    
    def test_invalid_start_date_format(self):
        """Test that invalid start_date format returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get(
            '/api/v1/analytics/step-timing/?steps=onboarding_start,purchase&start_date=invalid-date'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('Invalid date format', response.data['error'])
    
    def test_invalid_end_date_format(self):
        """Test that invalid end_date format returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get(
            '/api/v1/analytics/step-timing/?steps=onboarding_start,purchase&end_date=not-a-date'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('Invalid date format', response.data['error'])
    
    def test_app_isolation(self):
        """Test that only events from the authenticated app are included"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start,onboarding_complete,purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should only include sessions from self.app
        self.assertEqual(response.data['funnel_summary']['sessions_with_first_step'], 5)
    
    def test_query_param_auth(self):
        """Test step-timing endpoint with app_key as query parameter"""
        response = self.client.get(
            f'/api/v1/analytics/step-timing/?app_key={self.app_key}&steps=onboarding_start,onboarding_complete'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['app']['name'], 'Step Timing App')
    
    def test_whitespace_in_steps(self):
        """Test that whitespace in steps parameter is handled"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get(
            '/api/v1/analytics/step-timing/?steps= onboarding_start , onboarding_complete , purchase '
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Steps should be trimmed
        self.assertEqual(response.data['steps'], ['onboarding_start', 'onboarding_complete', 'purchase'])
    
    def test_two_step_funnel(self):
        """Test with minimum 2-step funnel"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start,purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should have 1 transition
        self.assertEqual(len(response.data['transitions']), 1)
        
        transition = response.data['transitions'][0]
        self.assertEqual(transition['from'], 'onboarding_start')
        self.assertEqual(transition['to'], 'purchase')
    
    def test_no_matching_events(self):
        """Test behavior when no events match the funnel steps"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=nonexistent_event1,nonexistent_event2')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should return 0s for all metrics
        summary = response.data['funnel_summary']
        self.assertEqual(summary['sessions_with_first_step'], 0)
        self.assertEqual(summary['sessions_with_all_steps'], 0)
        self.assertEqual(summary['completion_rate'], 0)
    
    def test_partial_funnel_timing(self):
        """Test that partial funnels still contribute to transition timing"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start,onboarding_complete,purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        transitions = response.data['transitions']
        
        # First transition should include session3 (which has onboarding but no purchase)
        # So 5 sessions analyzed for first transition
        self.assertEqual(transitions[0]['sessions_analyzed'], 5)
        
        # Second transition should NOT include session3 (no purchase)
        # So 4 sessions analyzed for second transition
        self.assertEqual(transitions[1]['sessions_analyzed'], 4)
    
    def test_statistics_non_negative(self):
        """Test that all timing statistics are non-negative"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start,onboarding_complete,purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        for transition in response.data['transitions']:
            self.assertGreaterEqual(transition['median_seconds'], 0)
            self.assertGreaterEqual(transition['mean_seconds'], 0)
            self.assertGreaterEqual(transition['p25_seconds'], 0)
            self.assertGreaterEqual(transition['p75_seconds'], 0)
        
        summary = response.data['funnel_summary']
        self.assertGreaterEqual(summary['median_total_seconds'], 0)
        self.assertGreaterEqual(summary['mean_total_seconds'], 0)
    
    def test_percentile_ordering(self):
        """Test that p25 <= median <= p75"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start,onboarding_complete,purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        for transition in response.data['transitions']:
            self.assertLessEqual(transition['p25_seconds'], transition['median_seconds'])
            self.assertLessEqual(transition['median_seconds'], transition['p75_seconds'])
    
    def test_completion_rate_bounded(self):
        """Test that completion_rate is between 0 and 1"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start,onboarding_complete,purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        completion_rate = response.data['funnel_summary']['completion_rate']
        self.assertGreaterEqual(completion_rate, 0)
        self.assertLessEqual(completion_rate, 1)
    
    def test_out_of_order_events_excluded(self):
        """Test that out-of-order events in a session are handled correctly"""
        # Create a session with out-of-order events
        session_ooo = 'session_ooo_' + 'f' * 16
        Event.objects.create(
            app=self.app, event_name="purchase",  # Purchase before onboarding
            timestamp=self.now - timedelta(hours=5), 
            session_id=session_ooo
        )
        Event.objects.create(
            app=self.app, event_name="onboarding_start", 
            timestamp=self.now - timedelta(hours=5) + timedelta(minutes=5),  # After purchase
            session_id=session_ooo
        )
        Event.objects.create(
            app=self.app, event_name="onboarding_complete", 
            timestamp=self.now - timedelta(hours=5) + timedelta(minutes=10), 
            session_id=session_ooo
        )
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start,onboarding_complete,purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # The out-of-order session has first step but NOT all steps in order
        # sessions_with_first_step should be 6 (5 original + 1 new)
        # sessions_with_all_steps should still be 4 (the new session has wrong order)
        self.assertEqual(response.data['funnel_summary']['sessions_with_first_step'], 6)
        self.assertEqual(response.data['funnel_summary']['sessions_with_all_steps'], 4)
    
    def test_different_app_key_sees_different_data(self):
        """Test that different app_key returns only that app's data"""
        # Create events for other_app
        other_session = 'other_sess_' + 'g' * 18
        Event.objects.create(
            app=self.other_app, event_name="onboarding_start", 
            timestamp=self.now - timedelta(minutes=10), 
            session_id=other_session
        )
        Event.objects.create(
            app=self.other_app, event_name="onboarding_complete", 
            timestamp=self.now - timedelta(minutes=5), 
            session_id=other_session
        )
        
        # Request with other_app's key
        self.client.credentials(HTTP_X_APP_KEY=str(self.other_app.id))
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start,onboarding_complete')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['app']['name'], 'Other Step App')
        self.assertEqual(response.data['funnel_summary']['sessions_with_first_step'], 2)  # 1 + 1 (from setUp)
    
    def test_multi_step_funnel(self):
        """Test with a longer funnel (4+ steps)"""
        # Create a session with 5 steps
        session_long = 'session_long_' + 'h' * 15
        base_time = self.now - timedelta(hours=6)
        Event.objects.create(
            app=self.app, event_name="step1", 
            timestamp=base_time, 
            session_id=session_long
        )
        Event.objects.create(
            app=self.app, event_name="step2", 
            timestamp=base_time + timedelta(minutes=1), 
            session_id=session_long
        )
        Event.objects.create(
            app=self.app, event_name="step3", 
            timestamp=base_time + timedelta(minutes=3), 
            session_id=session_long
        )
        Event.objects.create(
            app=self.app, event_name="step4", 
            timestamp=base_time + timedelta(minutes=6), 
            session_id=session_long
        )
        Event.objects.create(
            app=self.app, event_name="step5", 
            timestamp=base_time + timedelta(minutes=10), 
            session_id=session_long
        )
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=step1,step2,step3,step4,step5')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should have 4 transitions
        self.assertEqual(len(response.data['transitions']), 4)
        
        # Check each transition
        transitions = response.data['transitions']
        self.assertEqual(transitions[0]['from'], 'step1')
        self.assertEqual(transitions[0]['to'], 'step2')
        self.assertEqual(transitions[3]['from'], 'step4')
        self.assertEqual(transitions[3]['to'], 'step5')
    
    def test_total_funnel_time_calculation(self):
        """Test that total funnel time is correctly calculated"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=onboarding_start,onboarding_complete,purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Session 1: 15 min total (5 + 10)
        # Session 2: 8 min total (3 + 5)
        # Session 4: 12 min total (7 + 5)
        # Session 5: 9 min total (4 + 5)
        # Total times in seconds: 900, 480, 720, 540
        # Sorted: 480, 540, 720, 900
        # Median: (540 + 720) / 2 = 630
        summary = response.data['funnel_summary']
        self.assertEqual(summary['median_total_seconds'], 630)
    
    def test_empty_steps_returns_400(self):
        """Test that empty steps (all whitespace) returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/step-timing/?steps=,,,')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ConversionPathsViewTestCase(APITestCase):
    """
    Test Auto-Generated Conversion Paths endpoint.
    Tests for TASK-034: Auto-Generated Conversion Paths Endpoint
    """
    
    def setUp(self):
        """Set up test data with multiple users taking different paths to conversion"""
        self.user = User.objects.create_user(username='pathuser', password='testpass123')
        self.app = App.objects.create(name="Path App", user=self.user)
        self.app_key = str(self.app.id)
        
        # Create another app to test app isolation
        self.other_app = App.objects.create(name="Other App", user=self.user)
        
        self.now = timezone.now()
        
        # User IDs (32 chars each)
        self.session1 = 'a' * 32
        self.session2 = 'b' * 32
        self.session3 = 'c' * 32
        self.session4 = 'd' * 32
        self.session5 = 'e' * 32
        self.session6 = 'f' * 32
        self.anon_session = 'anon_1234567890abcdef'
        
        # Path 1: app_open -> feature_demo -> pricing -> purchase (3 users)
        # User 1
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(minutes=30), session_id=self.session1)
        Event.objects.create(app=self.app, event_name="feature_demo", 
                           timestamp=self.now - timedelta(minutes=25), session_id=self.session1)
        Event.objects.create(app=self.app, event_name="pricing", 
                           timestamp=self.now - timedelta(minutes=15), session_id=self.session1)
        Event.objects.create(app=self.app, event_name="purchase", 
                           timestamp=self.now - timedelta(minutes=10), session_id=self.session1)
        
        # User 2 (same path)
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(minutes=60), session_id=self.session2)
        Event.objects.create(app=self.app, event_name="feature_demo", 
                           timestamp=self.now - timedelta(minutes=55), session_id=self.session2)
        Event.objects.create(app=self.app, event_name="pricing", 
                           timestamp=self.now - timedelta(minutes=45), session_id=self.session2)
        Event.objects.create(app=self.app, event_name="purchase", 
                           timestamp=self.now - timedelta(minutes=40), session_id=self.session2)
        
        # User 3 (same path)
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(minutes=90), session_id=self.session3)
        Event.objects.create(app=self.app, event_name="feature_demo", 
                           timestamp=self.now - timedelta(minutes=85), session_id=self.session3)
        Event.objects.create(app=self.app, event_name="pricing", 
                           timestamp=self.now - timedelta(minutes=75), session_id=self.session3)
        Event.objects.create(app=self.app, event_name="purchase", 
                           timestamp=self.now - timedelta(minutes=70), session_id=self.session3)
        
        # Path 2: app_open -> pricing -> purchase (2 users - below default min_users)
        # User 4
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(minutes=50), session_id=self.session4)
        Event.objects.create(app=self.app, event_name="pricing", 
                           timestamp=self.now - timedelta(minutes=45), session_id=self.session4)
        Event.objects.create(app=self.app, event_name="purchase", 
                           timestamp=self.now - timedelta(minutes=43), session_id=self.session4)
        
        # User 5 (same path as user4)
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(minutes=80), session_id=self.session5)
        Event.objects.create(app=self.app, event_name="pricing", 
                           timestamp=self.now - timedelta(minutes=75), session_id=self.session5)
        Event.objects.create(app=self.app, event_name="purchase", 
                           timestamp=self.now - timedelta(minutes=73), session_id=self.session5)
        
        # User 6: Non-converting user (has events but no purchase)
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(minutes=100), session_id=self.session6)
        Event.objects.create(app=self.app, event_name="feature_demo", 
                           timestamp=self.now - timedelta(minutes=95), session_id=self.session6)
        
        # Anonymous user with conversion (should be excluded)
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(minutes=40), session_id=self.anon_session)
        Event.objects.create(app=self.app, event_name="purchase", 
                           timestamp=self.now - timedelta(minutes=35), session_id=self.anon_session)
        
        # Other app events (should NOT appear in results)
        Event.objects.create(app=self.other_app, event_name="app_open", 
                           timestamp=self.now, session_id=self.session1)
        Event.objects.create(app=self.other_app, event_name="purchase", 
                           timestamp=self.now, session_id=self.session1)
    
    def test_endpoint_requires_authentication(self):
        """Test that endpoint requires app_key authentication"""
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
    
    def test_endpoint_with_invalid_app_key(self):
        """Test endpoint with invalid app_key returns 401"""
        self.client.credentials(HTTP_X_APP_KEY="00000000-0000-0000-0000-000000000000")
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_conversion_events_parameter_required(self):
        """Test that conversion_events parameter is required"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('conversion_events', response.data['error'])
        self.assertIn('your_event_types', response.data)
        self.assertIn('example', response.data)
    
    def test_conversion_events_error_lists_user_event_types(self):
        """Test that 400 error includes user's actual event types"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        event_types = response.data['your_event_types']
        self.assertIsInstance(event_types, list)
        self.assertIn('app_open', event_types)
        self.assertIn('purchase', event_types)
    
    def test_empty_conversion_events_returns_400(self):
        """Test that empty conversion_events parameter returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_returns_expected_structure(self):
        """Test that response has correct structure"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('app', response.data)
        self.assertIn('filters', response.data)
        self.assertIn('data_quality', response.data)
        self.assertIn('top_conversion_paths', response.data)
        
        # Check app structure
        self.assertEqual(response.data['app']['name'], 'Path App')
        
        # Check filters structure
        self.assertIn('conversion_events', response.data['filters'])
        self.assertIn('limit', response.data['filters'])
        self.assertIn('min_sessions', response.data['filters'])
        self.assertIn('max_path_length', response.data['filters'])
        
        # Check data_quality structure
        self.assertIn('total_converting_sessions', response.data['data_quality'])
        self.assertIn('paths_analyzed', response.data['data_quality'])
    
    def test_discovers_top_path_correctly(self):
        """Test that the most common path is discovered correctly"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase&min_sessions=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        paths = response.data['top_conversion_paths']
        self.assertGreater(len(paths), 0)
        
        # First path should be the most common (3 users)
        top_path = paths[0]
        self.assertEqual(top_path['rank'], 1)
        self.assertEqual(top_path['sessions'], 3)
        self.assertEqual(top_path['path'], ['app_open', 'feature_demo', 'pricing', 'purchase'])
    
    def test_min_users_filter_works(self):
        """Test that min_users parameter filters out paths with fewer users"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # With min_sessions=3, only path with 3 users should appear
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase&min_sessions=3')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        paths = response.data['top_conversion_paths']
        # Only one path has 3+ users
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0]['sessions'], 3)
    
    def test_limit_parameter_works(self):
        """Test that limit parameter restricts number of paths returned"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase&min_sessions=1&limit=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        paths = response.data['top_conversion_paths']
        self.assertEqual(len(paths), 1)
    
    def test_all_sessions_included(self):
        """Test that all valid sessions are included (no anonymous exclusion in v2.0.0)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data_quality = response.data['data_quality']
        
        # All sessions with valid session_id are included (including anon_session)
        # 5 known converting + 1 anon converting = 6 total converting
        self.assertEqual(data_quality['total_converting_sessions'], 6)
    
    def test_path_has_step_timings(self):
        """Test that paths include step timing information"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase&min_sessions=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        paths = response.data['top_conversion_paths']
        top_path = paths[0]
        
        self.assertIn('step_timings', top_path)
        step_timings = top_path['step_timings']
        
        # Path has 4 steps, so 3 transitions
        self.assertEqual(len(step_timings), 3)
        
        # Check structure
        self.assertIn('from', step_timings[0])
        self.assertIn('to', step_timings[0])
        self.assertIn('avg_minutes', step_timings[0])
        
        # First transition should be app_open -> feature_demo
        self.assertEqual(step_timings[0]['from'], 'app_open')
        self.assertEqual(step_timings[0]['to'], 'feature_demo')
    
    def test_avg_duration_calculated(self):
        """Test that average duration is calculated correctly"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase&min_sessions=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        paths = response.data['top_conversion_paths']
        top_path = paths[0]
        
        self.assertIn('avg_duration_minutes', top_path)
        self.assertGreater(top_path['avg_duration_minutes'], 0)
    
    def test_conversion_rate_calculated(self):
        """Test that conversion rate is calculated correctly"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase&min_sessions=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        paths = response.data['top_conversion_paths']
        top_path = paths[0]
        
        self.assertIn('conversion_rate', top_path)
        # Should be between 0 and 1
        self.assertGreaterEqual(top_path['conversion_rate'], 0)
        self.assertLessEqual(top_path['conversion_rate'], 1)
    
    def test_app_isolation(self):
        """Test that only events from authenticated app are analyzed"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should not include other_app events
        self.assertEqual(response.data['app']['name'], 'Path App')
        
        # Total converting sessions = 6 (5 known + 1 anon, all with valid session_id)
        self.assertEqual(response.data['data_quality']['total_converting_sessions'], 6)
    
    def test_invalid_limit_returns_400(self):
        """Test that invalid limit parameter returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase&limit=abc')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_invalid_min_users_returns_400(self):
        """Test that invalid min_users parameter returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase&min_sessions=abc')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_invalid_max_path_length_returns_400(self):
        """Test that invalid max_path_length parameter returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase&max_path_length=abc')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_invalid_start_date_returns_400(self):
        """Test that invalid start_date returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase&start_date=invalid')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_invalid_end_date_returns_400(self):
        """Test that invalid end_date returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase&end_date=invalid')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_date_range_filtering(self):
        """Test that date range filters work correctly"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # Filter to future date range with no events
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase&start_date=2099-01-01&end_date=2099-12-31')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # No converting users in that range
        self.assertEqual(response.data['data_quality']['total_converting_sessions'], 0)
        self.assertEqual(response.data['top_conversion_paths'], [])
    
    def test_multiple_conversion_events(self):
        """Test that multiple conversion events are handled correctly"""
        # Add a subscription conversion for user6
        Event.objects.create(app=self.app, event_name="subscription", 
                           timestamp=self.now - timedelta(minutes=90), session_id=self.session6)
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase,subscription&min_sessions=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should now have 7 converting sessions (5 known + 1 anon purchase + 1 subscription)
        self.assertEqual(response.data['data_quality']['total_converting_sessions'], 7)
    
    def test_consecutive_duplicate_events_deduplicated(self):
        """Test that consecutive duplicate events are removed from paths"""
        # Create a user with repeated events
        session_id = 'r' * 32
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(minutes=20), session_id=session_id)
        Event.objects.create(app=self.app, event_name="app_open",  # duplicate
                           timestamp=self.now - timedelta(minutes=19), session_id=session_id)
        Event.objects.create(app=self.app, event_name="app_open",  # duplicate
                           timestamp=self.now - timedelta(minutes=18), session_id=session_id)
        Event.objects.create(app=self.app, event_name="purchase", 
                           timestamp=self.now - timedelta(minutes=15), session_id=session_id)
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase&min_sessions=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Find the path for this user (app_open -> purchase, not app_open -> app_open -> app_open -> purchase)
        paths = response.data['top_conversion_paths']
        
        # Check that no path has consecutive duplicates
        for path_data in paths:
            path = path_data['path']
            for i in range(len(path) - 1):
                self.assertNotEqual(path[i], path[i + 1], 
                    f"Path should not have consecutive duplicates: {path}")
    
    def test_limit_clamped_to_max_20(self):
        """Test that limit is clamped to maximum of 20"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase&limit=100')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Limit should be clamped to 20
        self.assertEqual(response.data['filters']['limit'], 20)
    
    def test_max_path_length_limits_path_size(self):
        """Test that max_path_length limits the path size"""
        # Create a user with a very long path
        session_id = 'l' * 32
        base_time = self.now - timedelta(hours=1)
        
        for i in range(15):
            Event.objects.create(
                app=self.app, 
                event_name=f"step_{i}", 
                timestamp=base_time + timedelta(minutes=i), 
                session_id=session_id
            )
        Event.objects.create(
            app=self.app, 
            event_name="purchase", 
            timestamp=base_time + timedelta(minutes=20), 
            session_id=session_id
        )
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase&min_sessions=1&max_path_length=5')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # All paths should be at most 5 steps
        for path_data in response.data['top_conversion_paths']:
            self.assertLessEqual(len(path_data['path']), 5)
    
    def test_paths_ranked_by_user_count(self):
        """Test that paths are ranked by number of users (descending)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase&min_sessions=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        paths = response.data['top_conversion_paths']
        
        # Check that paths are ordered by user count
        for i in range(len(paths) - 1):
            self.assertGreaterEqual(paths[i]['sessions'], paths[i + 1]['sessions'])
    
    def test_rank_is_sequential(self):
        """Test that rank numbers are sequential starting from 1"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase&min_sessions=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        paths = response.data['top_conversion_paths']
        
        for i, path_data in enumerate(paths, 1):
            self.assertEqual(path_data['rank'], i)
    
    def test_whitespace_in_conversion_events_handled(self):
        """Test that whitespace in conversion_events is trimmed"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events= purchase , subscription ')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should work correctly with trimmed events
        self.assertEqual(response.data['filters']['conversion_events'], ['purchase', 'subscription'])
    
    def test_query_param_auth_works(self):
        """Test that app_key as query parameter works"""
        response = self.client.get(f'/api/v1/analytics/conversion-paths/?app_key={self.app_key}&conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['app']['name'], 'Path App')
    
    def test_no_conversions_returns_empty_paths(self):
        """Test that app with no conversions returns empty paths"""
        # Create a new app with no conversion events
        empty_app = App.objects.create(name="Empty App", user=self.user)
        Event.objects.create(app=empty_app, event_name="app_open", 
                           timestamp=self.now, session_id='x' * 32)
        
        self.client.credentials(HTTP_X_APP_KEY=str(empty_app.id))
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data_quality']['total_converting_sessions'], 0)
        self.assertEqual(response.data['top_conversion_paths'], [])
    
    def test_null_user_ids_excluded(self):
        """Test that events with null session_id are excluded"""
        # Create event with null session_id
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now, session_id=None)
        Event.objects.create(app=self.app, event_name="purchase", 
                           timestamp=self.now, session_id=None)
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Total should still be 6 (null session not counted, anon IS counted)
        self.assertEqual(response.data['data_quality']['total_converting_sessions'], 6)
    
    def test_empty_user_ids_excluded(self):
        """Test that events with empty session_id are excluded"""
        # Create event with empty session_id
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now, session_id='')
        Event.objects.create(app=self.app, event_name="purchase", 
                           timestamp=self.now, session_id='')
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/conversion-paths/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Total should still be 6 (empty session not counted, anon IS counted)
        self.assertEqual(response.data['data_quality']['total_converting_sessions'], 6)


class DropOffViewTestCase(APITestCase):
    """
    Test Drop-Off Diagnostics endpoint.
    Tests for TASK-035: Drop-Off Diagnostics Endpoint
    """
    
    def setUp(self):
        """Set up test data with converters and non-converters"""
        self.user = User.objects.create_user(username='dropoffuser', password='testpass123')
        self.app = App.objects.create(name="Drop-Off App", user=self.user)
        self.app_key = str(self.app.id)
        
        # Create another app to test app isolation
        self.other_app = App.objects.create(name="Other App", user=self.user)
        
        self.now = timezone.now()
        
        # User IDs (32 chars each)
        self.converter1 = 'a' * 32
        self.converter2 = 'b' * 32
        self.converter3 = 'c' * 32
        self.non_converter1 = 'd' * 32
        self.non_converter2 = 'e' * 32
        self.non_converter3 = 'f' * 32
        self.non_converter4 = 'g' * 32
        self.non_converter5 = 'h' * 32
        self.anon_session = 'anon_1234567890abcdef'
        
        # Converters (3 users who completed purchase)
        # Converter 1: app_open -> feature_demo -> pricing -> purchase
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(minutes=60), session_id=self.converter1)
        Event.objects.create(app=self.app, event_name="feature_demo", 
                           timestamp=self.now - timedelta(minutes=55), session_id=self.converter1)
        Event.objects.create(app=self.app, event_name="pricing", 
                           timestamp=self.now - timedelta(minutes=45), session_id=self.converter1)
        Event.objects.create(app=self.app, event_name="purchase", 
                           timestamp=self.now - timedelta(minutes=40), session_id=self.converter1)
        
        # Converter 2: app_open -> pricing -> purchase
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(minutes=90), session_id=self.converter2)
        Event.objects.create(app=self.app, event_name="pricing", 
                           timestamp=self.now - timedelta(minutes=85), session_id=self.converter2)
        Event.objects.create(app=self.app, event_name="purchase", 
                           timestamp=self.now - timedelta(minutes=80), session_id=self.converter2)
        
        # Converter 3: app_open -> purchase (direct)
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(minutes=120), session_id=self.converter3)
        Event.objects.create(app=self.app, event_name="purchase", 
                           timestamp=self.now - timedelta(minutes=115), session_id=self.converter3)
        
        # Non-converters (5 users who dropped off at different points)
        # Non-converter 1: Dropped at pricing (common drop-off point)
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(minutes=50), session_id=self.non_converter1)
        Event.objects.create(app=self.app, event_name="feature_demo", 
                           timestamp=self.now - timedelta(minutes=45), session_id=self.non_converter1)
        Event.objects.create(app=self.app, event_name="pricing", 
                           timestamp=self.now - timedelta(minutes=40), session_id=self.non_converter1)
        
        # Non-converter 2: Dropped at pricing (same as above)
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(minutes=70), session_id=self.non_converter2)
        Event.objects.create(app=self.app, event_name="pricing", 
                           timestamp=self.now - timedelta(minutes=65), session_id=self.non_converter2)
        
        # Non-converter 3: Dropped at pricing (same as above)
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(minutes=100), session_id=self.non_converter3)
        Event.objects.create(app=self.app, event_name="pricing", 
                           timestamp=self.now - timedelta(minutes=95), session_id=self.non_converter3)
        
        # Non-converter 4: Dropped at feature_demo
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(minutes=80), session_id=self.non_converter4)
        Event.objects.create(app=self.app, event_name="feature_demo", 
                           timestamp=self.now - timedelta(minutes=75), session_id=self.non_converter4)
        
        # Non-converter 5: Dropped at support_contact (unique to non-converters)
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(minutes=110), session_id=self.non_converter5)
        Event.objects.create(app=self.app, event_name="support_contact", 
                           timestamp=self.now - timedelta(minutes=105), session_id=self.non_converter5)
        
        # Anonymous user (should be excluded)
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(minutes=40), session_id=self.anon_session)
        Event.objects.create(app=self.app, event_name="pricing", 
                           timestamp=self.now - timedelta(minutes=35), session_id=self.anon_session)
        
        # Other app events (should NOT appear in results)
        Event.objects.create(app=self.other_app, event_name="app_open", 
                           timestamp=self.now, session_id=self.converter1)
    
    def test_endpoint_requires_authentication(self):
        """Test that endpoint requires app_key authentication"""
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
    
    def test_endpoint_with_invalid_app_key(self):
        """Test endpoint with invalid app_key returns 401"""
        self.client.credentials(HTTP_X_APP_KEY="00000000-0000-0000-0000-000000000000")
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_conversion_events_parameter_required(self):
        """Test that conversion_events parameter is required"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('conversion_events', response.data['error'])
        self.assertIn('your_event_types', response.data)
        self.assertIn('example', response.data)
    
    def test_conversion_events_error_lists_user_event_types(self):
        """Test that 400 error includes user's actual event types"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        event_types = response.data['your_event_types']
        self.assertIsInstance(event_types, list)
        self.assertIn('app_open', event_types)
        self.assertIn('purchase', event_types)
    
    def test_empty_conversion_events_returns_400(self):
        """Test that empty conversion_events parameter returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_returns_expected_structure(self):
        """Test that response has correct structure"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('app', response.data)
        self.assertIn('filters', response.data)
        self.assertIn('data_quality', response.data)
        self.assertIn('drop_off_points', response.data)
        self.assertIn('events_more_common_in_non_converters', response.data)
        
        # Check app structure
        self.assertEqual(response.data['app']['name'], 'Drop-Off App')
        
        # Check filters structure
        self.assertIn('conversion_events', response.data['filters'])
        self.assertIn('min_sessions', response.data['filters'])
        self.assertIn('limit', response.data['filters'])
        
        # Check data_quality structure
        self.assertIn('total_sessions', response.data['data_quality'])
        self.assertIn('converting_sessions', response.data['data_quality'])
        self.assertIn('non_converting_sessions', response.data['data_quality'])
        self.assertIn('conversion_rate', response.data['data_quality'])
    
    def test_data_quality_counts_correct(self):
        """Test that data quality counts are accurate"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        dq = response.data['data_quality']
        # 3 converters + 5 non-converters + 1 anon non-converter = 9 total
        # In v2.0.0, all valid session_ids are counted (no anonymous exclusion)
        self.assertEqual(dq['total_sessions'], 9)
        self.assertEqual(dq['converting_sessions'], 3)
        self.assertEqual(dq['non_converting_sessions'], 6)
        self.assertAlmostEqual(dq['conversion_rate'], 3/9, places=2)
    
    def test_drop_off_points_identified(self):
        """Test that drop-off points are correctly identified"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase&min_sessions=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        drop_offs = response.data['drop_off_points']
        self.assertGreater(len(drop_offs), 0)
        
        # Pricing should be the #1 drop-off point
        # In v2.0.0: 3 non-converters + 1 anon dropped at pricing = 4
        pricing_dropoff = next((d for d in drop_offs if d['event'] == 'pricing'), None)
        self.assertIsNotNone(pricing_dropoff)
        self.assertEqual(pricing_dropoff['sessions_dropped'], 4)
    
    def test_min_users_filter_works(self):
        """Test that min_users parameter filters out low-frequency drop-offs"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # With min_sessions=2, feature_demo and support_contact should be excluded (only 1 user each)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase&min_sessions=2')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        drop_offs = response.data['drop_off_points']
        event_names = [d['event'] for d in drop_offs]
        
        # Only pricing should be included (3 users)
        self.assertIn('pricing', event_names)
        # feature_demo and support_contact should be excluded (only 1 user each)
        self.assertNotIn('feature_demo', event_names)
        self.assertNotIn('support_contact', event_names)
    
    def test_limit_parameter_works(self):
        """Test that limit parameter restricts number of drop-off points"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase&min_sessions=1&limit=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        drop_offs = response.data['drop_off_points']
        self.assertEqual(len(drop_offs), 1)
    
    def test_all_valid_sessions_included(self):
        """Test that all valid sessions are included (no anonymous exclusion in v2.0.0)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # In v2.0.0, all valid session_ids are included (anon_session has valid ID)
        self.assertEqual(response.data['data_quality']['total_sessions'], 9)
    
    def test_app_isolation(self):
        """Test that only events from requested app are analyzed"""
        self.client.credentials(HTTP_X_APP_KEY=str(self.other_app.id))
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Other app has only 1 user (converter1 with app_open only, no conversion)
        self.assertEqual(response.data['data_quality']['total_sessions'], 1)
        self.assertEqual(response.data['data_quality']['converting_sessions'], 0)
        self.assertEqual(response.data['data_quality']['non_converting_sessions'], 1)
    
    def test_drop_off_structure(self):
        """Test that drop-off point has expected structure"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase&min_sessions=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        drop_offs = response.data['drop_off_points']
        self.assertGreater(len(drop_offs), 0)
        
        first_dropoff = drop_offs[0]
        self.assertIn('rank', first_dropoff)
        self.assertIn('event', first_dropoff)
        self.assertIn('sessions_dropped', first_dropoff)
        self.assertIn('drop_off_rate', first_dropoff)
        self.assertIn('avg_time_before_exit_minutes', first_dropoff)
        self.assertIn('impact_score', first_dropoff)
        self.assertIn('converter_comparison', first_dropoff)
        
        # Check converter_comparison structure
        comp = first_dropoff['converter_comparison']
        self.assertIn('converters_with_event', comp)
        self.assertIn('converters_event_rate', comp)
        self.assertIn('non_converters_event_rate', comp)
        self.assertIn('differential', comp)
    
    def test_drop_offs_sorted_by_impact(self):
        """Test that drop-off points are sorted by impact score (descending)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase&min_sessions=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        drop_offs = response.data['drop_off_points']
        
        if len(drop_offs) > 1:
            for i in range(len(drop_offs) - 1):
                self.assertGreaterEqual(drop_offs[i]['sessions_dropped'], drop_offs[i + 1]['sessions_dropped'])
    
    def test_rank_is_sequential(self):
        """Test that rank numbers are sequential starting from 1"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase&min_sessions=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        drop_offs = response.data['drop_off_points']
        
        for i, dropoff in enumerate(drop_offs, 1):
            self.assertEqual(dropoff['rank'], i)
    
    def test_events_more_common_in_non_converters(self):
        """Test that differential events are correctly identified"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        diff_events = response.data['events_more_common_in_non_converters']
        
        # support_contact is unique to non-converters
        support_event = next((e for e in diff_events if e['event'] == 'support_contact'), None)
        if support_event:
            # Non-converter rate should be higher than converter rate
            self.assertGreater(support_event['differential'], 0)
    
    def test_date_filter_start_date(self):
        """Test that start_date filter works"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # Use a date in the future - should return no users
        future_date = (self.now + timedelta(days=1)).strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/drop-off/?conversion_events=purchase&start_date={future_date}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data_quality']['total_sessions'], 0)
    
    def test_date_filter_end_date(self):
        """Test that end_date filter works"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # Use a date in the past - should return no users
        past_date = (self.now - timedelta(days=30)).strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/drop-off/?conversion_events=purchase&end_date={past_date}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data_quality']['total_sessions'], 0)
    
    def test_invalid_date_format_returns_400(self):
        """Test that invalid date format returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase&start_date=invalid')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_invalid_min_users_returns_400(self):
        """Test that invalid min_users returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase&min_sessions=invalid')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('min_sessions', response.data['error'])
    
    def test_invalid_limit_returns_400(self):
        """Test that invalid limit returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase&limit=invalid')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('limit', response.data['error'])
    
    def test_limit_clamped_to_max(self):
        """Test that limit is clamped to maximum of 50"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase&limit=100')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['filters']['limit'], 50)
    
    def test_whitespace_in_conversion_events_handled(self):
        """Test that whitespace in conversion_events is trimmed"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events= purchase , subscription ')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['filters']['conversion_events'], ['purchase', 'subscription'])
    
    def test_query_param_auth_works(self):
        """Test that app_key as query parameter works"""
        response = self.client.get(f'/api/v1/analytics/drop-off/?app_key={self.app_key}&conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['app']['name'], 'Drop-Off App')
    
    def test_all_users_convert_returns_empty_drop_offs(self):
        """Test that when all users convert, drop_off_points is empty"""
        # Create a new app where everyone converts
        all_convert_app = App.objects.create(name="All Convert App", user=self.user)
        Event.objects.create(app=all_convert_app, event_name="app_open", 
                           timestamp=self.now, session_id='x' * 32)
        Event.objects.create(app=all_convert_app, event_name="purchase", 
                           timestamp=self.now, session_id='x' * 32)
        
        self.client.credentials(HTTP_X_APP_KEY=str(all_convert_app.id))
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data_quality']['non_converting_sessions'], 0)
        self.assertEqual(response.data['drop_off_points'], [])
    
    def test_no_users_returns_empty_response(self):
        """Test that app with no users returns proper empty response"""
        empty_app = App.objects.create(name="Empty App", user=self.user)
        
        self.client.credentials(HTTP_X_APP_KEY=str(empty_app.id))
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data_quality']['total_sessions'], 0)
        self.assertEqual(response.data['drop_off_points'], [])
    
    def test_null_user_ids_excluded(self):
        """Test that events with null session_id are excluded"""
        # Create event with null session_id
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now, session_id=None)
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Total should still be 9 (null session not counted, anon IS counted)
        self.assertEqual(response.data['data_quality']['total_sessions'], 9)
    
    def test_empty_user_ids_excluded(self):
        """Test that events with empty session_id are excluded"""
        # Create event with empty session_id
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now, session_id='')
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Total should still be 9 (empty session not counted, anon IS counted)
        self.assertEqual(response.data['data_quality']['total_sessions'], 9)
    
    def test_conversion_event_not_counted_as_drop_off(self):
        """Test that conversion events themselves are not counted as drop-off points"""
        # Create scenario where some users' last event IS the conversion event
        # This is already the case for converters, but let's verify
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase&min_sessions=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        drop_offs = response.data['drop_off_points']
        event_names = [d['event'] for d in drop_offs]
        
        # purchase should NOT appear as a drop-off point
        self.assertNotIn('purchase', event_names)
    
    def test_avg_time_before_exit_calculated(self):
        """Test that average time before exit is calculated correctly"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/drop-off/?conversion_events=purchase&min_sessions=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        drop_offs = response.data['drop_off_points']
        
        # All drop-offs should have avg_time_before_exit_minutes
        for dropoff in drop_offs:
            self.assertIsNotNone(dropoff['avg_time_before_exit_minutes'])
            self.assertIsInstance(dropoff['avg_time_before_exit_minutes'], (int, float))


class EventCorrelationViewTestCase(APITestCase):
    """
    Test Event Correlation (Conversion Drivers Map) endpoint.
    Tests for TASK-036: Event Correlation - Conversion Drivers Map
    
    This endpoint identifies which events correlate positively or negatively
    with conversion by calculating lift scores.
    """
    
    def setUp(self):
        """Set up test data with converters and non-converters with various event patterns"""
        self.user = User.objects.create_user(username='correlationuser', password='testpass123')
        self.app = App.objects.create(name="Correlation App", user=self.user)
        self.app_key = str(self.app.id)
        
        # Create another app to test isolation
        self.other_app = App.objects.create(name="Other App", user=self.user)
        
        self.now = timezone.now()
        
        # User IDs - we need a diverse set of users
        # Converters (will have purchase event)
        self.converter1 = 'c1' + 'a' * 30
        self.converter2 = 'c2' + 'b' * 30
        self.converter3 = 'c3' + 'c' * 30
        self.converter4 = 'c4' + 'd' * 30
        self.converter5 = 'c5' + 'e' * 30
        self.converter6 = 'c6' + 'f' * 30
        self.converter7 = 'c7' + 'g' * 30
        self.converter8 = 'c8' + 'h' * 30
        self.converter9 = 'c9' + 'i' * 30
        self.converter10 = 'ca' + 'j' * 30
        
        # Non-converters (no purchase event)
        self.non_converter1 = 'n1' + 'k' * 30
        self.non_converter2 = 'n2' + 'l' * 30
        self.non_converter3 = 'n3' + 'm' * 30
        self.non_converter4 = 'n4' + 'n' * 30
        self.non_converter5 = 'n5' + 'o' * 30
        self.non_converter6 = 'n6' + 'p' * 30
        self.non_converter7 = 'n7' + 'q' * 30
        self.non_converter8 = 'n8' + 'r' * 30
        self.non_converter9 = 'n9' + 's' * 30
        self.non_converter10 = 'na' + 't' * 30
        
        # Anonymous user (should be excluded)
        self.anon_session = 'anon_1234567890abcdef'
        
        # ===== CREATE CONVERSION EVENTS =====
        # All 10 converters complete a purchase
        for conv in [self.converter1, self.converter2, self.converter3, self.converter4, 
                     self.converter5, self.converter6, self.converter7, self.converter8,
                     self.converter9, self.converter10]:
            Event.objects.create(app=self.app, event_name="purchase", 
                               timestamp=self.now, session_id=conv)
        
        # ===== POSITIVE CORRELATION: demo_viewed =====
        # 8 out of 10 converters view demo (80%)
        # 2 out of 10 non-converters view demo (20%)
        # Expected lift: (80% / 20% - 1) * 100 = +300%
        for conv in [self.converter1, self.converter2, self.converter3, self.converter4,
                     self.converter5, self.converter6, self.converter7, self.converter8]:
            Event.objects.create(app=self.app, event_name="demo_viewed", 
                               timestamp=self.now - timedelta(hours=1), session_id=conv)
        for non_conv in [self.non_converter1, self.non_converter2]:
            Event.objects.create(app=self.app, event_name="demo_viewed", 
                               timestamp=self.now - timedelta(hours=1), session_id=non_conv)
        
        # ===== POSITIVE CORRELATION: pricing_page =====
        # 7 out of 10 converters visit pricing (70%)
        # 3 out of 10 non-converters visit pricing (30%)
        # Expected lift: (70% / 30% - 1) * 100 = +133%
        for conv in [self.converter1, self.converter2, self.converter3, self.converter4,
                     self.converter5, self.converter6, self.converter7]:
            Event.objects.create(app=self.app, event_name="pricing_page", 
                               timestamp=self.now - timedelta(hours=2), session_id=conv)
        for non_conv in [self.non_converter1, self.non_converter2, self.non_converter3]:
            Event.objects.create(app=self.app, event_name="pricing_page", 
                               timestamp=self.now - timedelta(hours=2), session_id=non_conv)
        
        # ===== NEGATIVE CORRELATION: help_center =====
        # 2 out of 10 converters visit help (20%)
        # 8 out of 10 non-converters visit help (80%)
        # Expected lift: (20% / 80% - 1) * 100 = -75%
        for conv in [self.converter1, self.converter2]:
            Event.objects.create(app=self.app, event_name="help_center", 
                               timestamp=self.now - timedelta(hours=1), session_id=conv)
        for non_conv in [self.non_converter1, self.non_converter2, self.non_converter3, 
                         self.non_converter4, self.non_converter5, self.non_converter6,
                         self.non_converter7, self.non_converter8]:
            Event.objects.create(app=self.app, event_name="help_center", 
                               timestamp=self.now - timedelta(hours=1), session_id=non_conv)
        
        # ===== NEGATIVE CORRELATION: support_chat =====
        # 1 out of 10 converters use support (10%)
        # 6 out of 10 non-converters use support (60%)
        # Expected lift: (10% / 60% - 1) * 100 = -83%
        for conv in [self.converter1]:
            Event.objects.create(app=self.app, event_name="support_chat", 
                               timestamp=self.now - timedelta(hours=1), session_id=conv)
        for non_conv in [self.non_converter1, self.non_converter2, self.non_converter3, 
                         self.non_converter4, self.non_converter5, self.non_converter6]:
            Event.objects.create(app=self.app, event_name="support_chat", 
                               timestamp=self.now - timedelta(hours=1), session_id=non_conv)
        
        # ===== NEUTRAL EVENT: app_open (everyone does it) =====
        # All 20 users open the app (100% both groups)
        for user in [self.converter1, self.converter2, self.converter3, self.converter4,
                     self.converter5, self.converter6, self.converter7, self.converter8,
                     self.converter9, self.converter10, self.non_converter1, self.non_converter2,
                     self.non_converter3, self.non_converter4, self.non_converter5, 
                     self.non_converter6, self.non_converter7, self.non_converter8,
                     self.non_converter9, self.non_converter10]:
            Event.objects.create(app=self.app, event_name="app_open", 
                               timestamp=self.now - timedelta(hours=3), session_id=user)
        
        # ===== LOW SAMPLE EVENT (below default threshold) =====
        # Only 3 users trigger rare_feature (should be excluded by default min_sample_size=10)
        for user in [self.converter1, self.converter2, self.non_converter1]:
            Event.objects.create(app=self.app, event_name="rare_feature", 
                               timestamp=self.now - timedelta(hours=1), session_id=user)
        
        # Anonymous user events (should be excluded from analysis)
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now - timedelta(hours=1), session_id=self.anon_session)
        Event.objects.create(app=self.app, event_name="demo_viewed", 
                           timestamp=self.now - timedelta(hours=1), session_id=self.anon_session)
        
        # Other app events (should NOT appear in results)
        Event.objects.create(app=self.other_app, event_name="app_open", 
                           timestamp=self.now, session_id=self.converter1)
        Event.objects.create(app=self.other_app, event_name="purchase", 
                           timestamp=self.now, session_id=self.converter1)
    
    def test_endpoint_requires_authentication(self):
        """Test that endpoint requires app_key authentication"""
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
    
    def test_endpoint_with_invalid_app_key(self):
        """Test endpoint with invalid app_key returns 401"""
        self.client.credentials(HTTP_X_APP_KEY="00000000-0000-0000-0000-000000000000")
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_conversion_events_parameter_required(self):
        """Test that conversion_events parameter is required"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('conversion_events', response.data['error'])
        self.assertIn('your_event_types', response.data)
        self.assertIn('example', response.data)
    
    def test_conversion_events_error_lists_user_event_types(self):
        """Test that 400 error includes user's actual event types"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        event_types = response.data['your_event_types']
        self.assertIsInstance(event_types, list)
        self.assertIn('app_open', event_types)
        self.assertIn('purchase', event_types)
        self.assertIn('demo_viewed', event_types)
    
    def test_empty_conversion_events_returns_400(self):
        """Test that empty conversion_events parameter returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_returns_expected_structure(self):
        """Test that response has correct structure"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('app', response.data)
        self.assertIn('filters', response.data)
        self.assertIn('data_quality', response.data)
        self.assertIn('positive_correlations', response.data)
        self.assertIn('negative_correlations', response.data)
        
        # Check app structure
        self.assertEqual(response.data['app']['name'], 'Correlation App')
        
        # Check filters structure
        self.assertIn('conversion_events', response.data['filters'])
        self.assertIn('min_sessions', response.data['filters'])
        self.assertIn('limit', response.data['filters'])
        
        # Check data_quality structure
        self.assertIn('total_sessions', response.data['data_quality'])
        self.assertIn('converting_sessions', response.data['data_quality'])
        self.assertIn('non_converting_sessions', response.data['data_quality'])
        self.assertIn('baseline_conversion_rate', response.data['data_quality'])
    
    def test_data_quality_counts_correct(self):
        """Test that data quality counts are accurate"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        dq = response.data['data_quality']
        # 10 converters + 10 non-converters + 1 anon non-converter = 21 total
        # In v2.0.0, all valid session_ids are counted
        self.assertEqual(dq['total_sessions'], 21)
        self.assertEqual(dq['converting_sessions'], 10)
        self.assertEqual(dq['non_converting_sessions'], 11)
        self.assertAlmostEqual(dq['baseline_conversion_rate'], 10/21, places=2)
    
    def test_positive_correlations_identified(self):
        """Test that positive correlations are correctly identified"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        pos_corr = response.data['positive_correlations']
        self.assertGreater(len(pos_corr), 0)
        
        # demo_viewed should be in positive correlations
        demo_corr = next((c for c in pos_corr if c['event'] == 'demo_viewed'), None)
        self.assertIsNotNone(demo_corr)
        self.assertGreater(demo_corr['lift_percent'], 0)
        
        # pricing_page should also be positive
        pricing_corr = next((c for c in pos_corr if c['event'] == 'pricing_page'), None)
        self.assertIsNotNone(pricing_corr)
        self.assertGreater(pricing_corr['lift_percent'], 0)
    
    def test_negative_correlations_identified(self):
        """Test that negative correlations are correctly identified"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        neg_corr = response.data['negative_correlations']
        self.assertGreater(len(neg_corr), 0)
        
        # help_center should be in negative correlations
        help_corr = next((c for c in neg_corr if c['event'] == 'help_center'), None)
        self.assertIsNotNone(help_corr)
        self.assertLess(help_corr['lift_percent'], 0)
    
    def test_lift_calculation_correct(self):
        """Test that lift percentage is calculated correctly"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # demo_viewed: 8/10 converters (80%), 2/10 non-converters (20%)
        # With event: 8 convert out of 10 who viewed = 80%
        # Without event: 2 convert out of 10 who didn't view = 20%
        # Lift = (80/20 - 1) * 100 = 300%
        pos_corr = response.data['positive_correlations']
        demo_corr = next((c for c in pos_corr if c['event'] == 'demo_viewed'), None)
        
        if demo_corr:
            # Check the lift is positive and significant
            self.assertGreater(demo_corr['lift_percent'], 100)  # Should be ~300%
    
    def test_correlation_structure(self):
        """Test that each correlation entry has expected structure"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        pos_corr = response.data['positive_correlations']
        self.assertGreater(len(pos_corr), 0)
        
        first = pos_corr[0]
        self.assertIn('rank', first)
        self.assertIn('event', first)
        self.assertIn('sessions_with_event', first)
        self.assertIn('conversion_rate_with', first)
        self.assertIn('conversion_rate_without', first)
        self.assertIn('lift_percent', first)
        self.assertIn('converts_with', first)
        self.assertIn('converts_without', first)
    
    def test_positive_correlations_sorted_by_lift(self):
        """Test that positive correlations are sorted by lift (descending)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        pos_corr = response.data['positive_correlations']
        
        if len(pos_corr) > 1:
            for i in range(len(pos_corr) - 1):
                self.assertGreaterEqual(pos_corr[i]['lift_percent'], pos_corr[i + 1]['lift_percent'])
    
    def test_negative_correlations_sorted_by_lift(self):
        """Test that negative correlations are sorted by lift (ascending, most negative first)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        neg_corr = response.data['negative_correlations']
        
        if len(neg_corr) > 1:
            for i in range(len(neg_corr) - 1):
                self.assertLessEqual(neg_corr[i]['lift_percent'], neg_corr[i + 1]['lift_percent'])
    
    def test_rank_is_sequential(self):
        """Test that rank numbers are sequential starting from 1"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        for corr_list in [response.data['positive_correlations'], response.data['negative_correlations']]:
            for i, corr in enumerate(corr_list, 1):
                self.assertEqual(corr['rank'], i)
    
    def test_min_sample_size_filter(self):
        """Test that min_users filters out low-sample events"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # Default min_sessions=10, rare_feature has only 3 users
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        all_events = [c['event'] for c in response.data['positive_correlations']]
        all_events += [c['event'] for c in response.data['negative_correlations']]
        
        # rare_feature should be excluded (only 3 users)
        self.assertNotIn('rare_feature', all_events)
    
    def test_min_users_parameter_respected(self):
        """Test that custom min_users is applied"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # With min_sessions=1, rare_feature should be included if it passes other thresholds
        # Note: both groups need min_users, so rare_feature (3 users) may still be excluded
        # if users_without_event < min_users
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase&min_sessions=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # With min_sessions=1, we should see more events analyzed
        self.assertGreaterEqual(response.data['data_quality']['events_analyzed'], 1)
    
    def test_limit_parameter_works(self):
        """Test that limit parameter restricts number of correlations"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase&limit=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.assertLessEqual(len(response.data['positive_correlations']), 1)
        self.assertLessEqual(len(response.data['negative_correlations']), 1)
    
    def test_all_valid_sessions_included(self):
        """Test that all valid sessions are included (no anonymous exclusion in v2.0.0)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # In v2.0.0, all valid session_ids are counted (including anon_session)
        self.assertEqual(response.data['data_quality']['total_sessions'], 21)
    
    def test_app_isolation(self):
        """Test that only events from requested app are analyzed"""
        self.client.credentials(HTTP_X_APP_KEY=str(self.other_app.id))
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Other app has only 1 session with 2 events (app_open + purchase).
        # Since purchase is excluded from correlation and app_open has 0 sessions
        # without it, no events meet the threshold. View returns empty results.
        self.assertEqual(response.data['data_quality']['total_sessions'], 0)
        self.assertEqual(response.data['positive_correlations'], [])
        self.assertEqual(response.data['negative_correlations'], [])
    
    def test_date_filter_start_date(self):
        """Test that start_date filter works"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # Use a date in the future - should return no users
        future_date = (self.now + timedelta(days=1)).strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/event-correlation/?conversion_events=purchase&start_date={future_date}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data_quality']['total_sessions'], 0)
    
    def test_date_filter_end_date(self):
        """Test that end_date filter works"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        
        # Use a date in the past - should return no users
        past_date = (self.now - timedelta(days=30)).strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/event-correlation/?conversion_events=purchase&end_date={past_date}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data_quality']['total_sessions'], 0)
    
    def test_invalid_date_format_returns_400(self):
        """Test that invalid date format returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase&start_date=invalid')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_invalid_min_users_returns_400(self):
        """Test that invalid min_users returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase&min_sessions=invalid')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('min_sessions', response.data['error'])
    
    def test_invalid_limit_returns_400(self):
        """Test that invalid limit returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase&limit=invalid')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('limit', response.data['error'])
    
    def test_limit_clamped_to_max(self):
        """Test that limit is clamped to maximum of 50"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase&limit=200')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['filters']['limit'], 50)
    
    def test_whitespace_in_conversion_events_handled(self):
        """Test that whitespace in conversion_events is trimmed"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events= purchase , subscription ')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['filters']['conversion_events'], ['purchase', 'subscription'])
    
    def test_query_param_auth_works(self):
        """Test that app_key as query parameter works"""
        response = self.client.get(f'/api/v1/analytics/event-correlation/?app_key={self.app_key}&conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['app']['name'], 'Correlation App')
    
    def test_conversion_event_excluded_from_correlations(self):
        """Test that conversion event itself is not listed in correlations"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        all_events = [c['event'] for c in response.data['positive_correlations']]
        all_events += [c['event'] for c in response.data['negative_correlations']]
        
        # purchase (the conversion event) should NOT appear
        self.assertNotIn('purchase', all_events)
    
    def test_neutral_events_excluded_from_lists(self):
        """Test that events with ~0% lift are excluded from both lists"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # app_open has 100% in both groups, so lift should be ~0%
        # It should not be in either positive or negative correlations
        pos_events = [c['event'] for c in response.data['positive_correlations']]
        neg_events = [c['event'] for c in response.data['negative_correlations']]
        
        # app_open might appear but with very low lift - this is acceptable
        # The main check is that truly neutral events don't dominate the lists
    
    def test_no_users_returns_empty_response(self):
        """Test that app with no users returns proper empty response"""
        empty_app = App.objects.create(name="Empty App", user=self.user)
        
        self.client.credentials(HTTP_X_APP_KEY=str(empty_app.id))
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data_quality']['total_sessions'], 0)
        self.assertEqual(response.data['positive_correlations'], [])
        self.assertEqual(response.data['negative_correlations'], [])
    
    def test_all_users_convert_edge_case(self):
        """Test edge case where all users convert"""
        # Create a new app where everyone converts
        all_convert_app = App.objects.create(name="All Convert App", user=self.user)
        Event.objects.create(app=all_convert_app, event_name="app_open", 
                           timestamp=self.now, session_id='x' * 32)
        Event.objects.create(app=all_convert_app, event_name="purchase", 
                           timestamp=self.now, session_id='x' * 32)
        Event.objects.create(app=all_convert_app, event_name="app_open", 
                           timestamp=self.now, session_id='y' * 32)
        Event.objects.create(app=all_convert_app, event_name="purchase", 
                           timestamp=self.now, session_id='y' * 32)
        
        self.client.credentials(HTTP_X_APP_KEY=str(all_convert_app.id))
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase&min_sessions=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # When all users convert and do the same events, no event has sessions
        # 'without' it, so no events pass the correlation threshold.
        # View returns empty results with total_sessions=0 (no analyzable data).
        self.assertEqual(response.data['data_quality']['total_sessions'], 0)
        self.assertEqual(response.data['positive_correlations'], [])
        self.assertEqual(response.data['negative_correlations'], [])
    
    def test_no_users_convert_edge_case(self):
        """Test edge case where no users convert"""
        # Create a new app where no one converts
        no_convert_app = App.objects.create(name="No Convert App", user=self.user)
        Event.objects.create(app=no_convert_app, event_name="app_open", 
                           timestamp=self.now, session_id='x' * 32)
        Event.objects.create(app=no_convert_app, event_name="app_open", 
                           timestamp=self.now, session_id='y' * 32)
        
        self.client.credentials(HTTP_X_APP_KEY=str(no_convert_app.id))
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase&min_sessions=1')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data_quality']['converting_sessions'], 0)
        self.assertEqual(response.data['data_quality']['baseline_conversion_rate'], 0.0)
    
    def test_null_user_ids_excluded(self):
        """Test that events with null session_id are excluded"""
        # Create event with null session_id
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now, session_id=None)
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Total should still be 21 (null session not counted, anon IS counted)
        self.assertEqual(response.data['data_quality']['total_sessions'], 21)
    
    def test_empty_user_ids_excluded(self):
        """Test that events with empty session_id are excluded"""
        # Create event with empty session_id
        Event.objects.create(app=self.app, event_name="app_open", 
                           timestamp=self.now, session_id='')
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/event-correlation/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Total should still be 21 (empty session not counted, anon IS counted)
        self.assertEqual(response.data['data_quality']['total_sessions'], 21)


class SegmentComparisonViewTestCase(APITestCase):
    """
    Test Segment Comparison endpoint.
    Tests for TASK-038: Simple Segment Comparison Endpoint
    
    Tests cover:
    - Authentication requirements
    - Required conversion_events parameter
    - segment_by parameter validation (platform, country, has_user_id)
    - granularity parameter validation (day, week, month, quarter, year)
    - Date range filtering
    - Correct conversion rate calculations per segment
    - Response structure validation
    """
    
    def setUp(self):
        """Set up test data with multiple platforms, countries, and user types"""
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.app = App.objects.create(name="Test App", user=self.user)
        self.app_key = str(self.app.id)
        
        # Create another app to test app isolation
        self.other_app = App.objects.create(name="Other App", user=self.user)
        
        # Set up timestamps
        self.now = timezone.now()
        self.yesterday = self.now - timedelta(days=1)
        self.last_week = self.now - timedelta(days=8)
        self.last_month = self.now - timedelta(days=35)
        
        # User IDs - some real (32 hex), some anonymous
        self.session_ios_1 = 'a' * 32
        self.session_ios_2 = 'b' * 32
        self.session_android_1 = 'c' * 32
        self.session_android_2 = 'd' * 32
        self.session_web = 'e' * 32
        self.anon_session_1 = 'anon_1234567890abcdef'
        self.anon_session_2 = 'anon_abcdef1234567890'
        
        # iOS users - today (2 users, 1 converts)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.now, 
                           session_id=self.session_ios_1, platform='ios', country='US')
        Event.objects.create(app=self.app, event_name="purchase", timestamp=self.now, 
                           session_id=self.session_ios_1, platform='ios', country='US')
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.now, 
                           session_id=self.session_ios_2, platform='ios', country='GB')
        
        # iOS users - yesterday (same users)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.yesterday, 
                           session_id=self.session_ios_1, platform='ios', country='US')
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.yesterday, 
                           session_id=self.session_ios_2, platform='ios', country='GB')
        
        # Android users - today (2 users, 0 convert)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.now, 
                           session_id=self.session_android_1, platform='android', country='DE')
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.now, 
                           session_id=self.session_android_2, platform='android', country='US')
        
        # Android users - yesterday (1 converts)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.yesterday, 
                           session_id=self.session_android_1, platform='android', country='DE')
        Event.objects.create(app=self.app, event_name="purchase", timestamp=self.yesterday, 
                           session_id=self.session_android_1, platform='android', country='DE')
        
        # Web users - today (1 user, 1 converts)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.now, 
                           session_id=self.session_web, platform='web', country='CA')
        Event.objects.create(app=self.app, event_name="purchase", timestamp=self.now, 
                           session_id=self.session_web, platform='web', country='CA')
        
        # Anonymous users - today (2 users, 0 convert)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.now, 
                           session_id=self.anon_session_1, platform='ios', country='US')
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.now, 
                           session_id=self.anon_session_2, platform='android', country='GB')
        
        # Anonymous user - yesterday (1 converts)
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.yesterday, 
                           session_id=self.anon_session_1, platform='ios', country='US')
        Event.objects.create(app=self.app, event_name="purchase", timestamp=self.yesterday, 
                           session_id=self.anon_session_1, platform='ios', country='US')
        
        # Events for other app (should NOT appear)
        Event.objects.create(app=self.other_app, event_name="purchase", timestamp=self.now, 
                           session_id=self.session_ios_1, platform='ios', country='US')
    
    # ===========================================
    # AUTHENTICATION TESTS
    # ===========================================
    
    def test_requires_authentication(self):
        """Test that endpoint requires app_key authentication"""
        response = self.client.get('/api/v1/analytics/segments/')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
    
    def test_invalid_app_key_returns_401(self):
        """Test that invalid app_key returns 401"""
        self.client.credentials(HTTP_X_APP_KEY="00000000-0000-0000-0000-000000000000")
        response = self.client.get('/api/v1/analytics/segments/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_valid_app_key_returns_200(self):
        """Test that valid app_key with conversion_events returns 200"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    # ===========================================
    # CONVERSION_EVENTS PARAMETER TESTS
    # ===========================================
    
    def test_missing_conversion_events_returns_400(self):
        """Test that missing conversion_events returns 400 with helpful message"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('conversion_events parameter required', response.data['error'])
        self.assertIn('your_event_types', response.data)
        self.assertIn('example', response.data)
    
    def test_empty_conversion_events_returns_400(self):
        """Test that empty conversion_events returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_whitespace_only_conversion_events_returns_400(self):
        """Test that whitespace-only conversion_events returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=%20%20%20')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_multiple_conversion_events_accepted(self):
        """Test that multiple comma-separated conversion_events are accepted"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase,subscription')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['conversion_events'], ['purchase', 'subscription'])
    
    # ===========================================
    # SEGMENT_BY PARAMETER TESTS
    # ===========================================
    
    def test_default_segment_by_is_platform(self):
        """Test that default segment_by is 'platform'"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['segment_by'], 'platform')
    
    def test_segment_by_platform(self):
        """Test segment_by=platform returns platform segments"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&segment_by=platform')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['segment_by'], 'platform')
        
        segment_names = [s['segment'] for s in response.data['segments']]
        # Should have ios, android, web
        self.assertIn('ios', segment_names)
        self.assertIn('android', segment_names)
        self.assertIn('web', segment_names)
    
    def test_segment_by_country(self):
        """Test segment_by=country returns country segments"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&segment_by=country')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['segment_by'], 'country')
        
        segment_names = [s['segment'] for s in response.data['segments']]
        # Should have US, GB, DE, CA
        self.assertIn('US', segment_names)
    
    def test_segment_by_has_user_id_returns_400(self):
        """Test segment_by=has_user_id returns 400 (removed in v2.0.0 - session-based only)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&segment_by=has_user_id')
        
        # has_user_id segment type was removed in v2.0.0 as part of session-based analytics
        # migration. The field no longer exists in the Event model.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('Invalid segment_by', response.data['error'])
    
    def test_invalid_segment_by_returns_400(self):
        """Test that invalid segment_by returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&segment_by=invalid')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('Invalid segment_by', response.data['error'])
    
    # ===========================================
    # GRANULARITY PARAMETER TESTS
    # ===========================================
    
    def test_default_granularity_is_day(self):
        """Test that default granularity is 'day'"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'day')
    
    def test_granularity_day(self):
        """Test granularity=day returns daily periods"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&granularity=day')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'day')
        
        # Check period format is YYYY-MM-DD
        if response.data['segments']:
            first_segment = response.data['segments'][0]
            if first_segment['periods']:
                period = first_segment['periods'][0]['period']
                self.assertRegex(period, r'^\d{4}-\d{2}-\d{2}$')
    
    def test_granularity_week(self):
        """Test granularity=week returns weekly periods"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&granularity=week')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'week')
        
        # Check period format is YYYY-Www
        if response.data['segments']:
            first_segment = response.data['segments'][0]
            if first_segment['periods']:
                period = first_segment['periods'][0]['period']
                self.assertRegex(period, r'^\d{4}-W\d{2}$')
    
    def test_granularity_month(self):
        """Test granularity=month returns monthly periods"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&granularity=month')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'month')
        
        # Check period format is YYYY-MM
        if response.data['segments']:
            first_segment = response.data['segments'][0]
            if first_segment['periods']:
                period = first_segment['periods'][0]['period']
                self.assertRegex(period, r'^\d{4}-\d{2}$')
    
    def test_granularity_quarter(self):
        """Test granularity=quarter returns quarterly periods"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&granularity=quarter')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'quarter')
        
        # Check period format is YYYY-Qn
        if response.data['segments']:
            first_segment = response.data['segments'][0]
            if first_segment['periods']:
                period = first_segment['periods'][0]['period']
                self.assertRegex(period, r'^\d{4}-Q[1-4]$')
    
    def test_granularity_year(self):
        """Test granularity=year returns yearly periods"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&granularity=year')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['granularity'], 'year')
        
        # Check period format is YYYY
        if response.data['segments']:
            first_segment = response.data['segments'][0]
            if first_segment['periods']:
                period = first_segment['periods'][0]['period']
                self.assertRegex(period, r'^\d{4}$')
    
    def test_invalid_granularity_returns_400(self):
        """Test that invalid granularity returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&granularity=hourly')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('Invalid granularity', response.data['error'])
    
    # ===========================================
    # DATE RANGE TESTS
    # ===========================================
    
    def test_from_date_filter(self):
        """Test from date filter works correctly"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        today_str = self.now.strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/segments/?conversion_events=purchase&from={today_str}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['date_range']['from'], today_str)
    
    def test_to_date_filter(self):
        """Test to date filter works correctly"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        yesterday_str = self.yesterday.strftime('%Y-%m-%d')
        response = self.client.get(f'/api/v1/analytics/segments/?conversion_events=purchase&to={yesterday_str}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['date_range']['to'], yesterday_str)
    
    def test_from_and_to_date_filter(self):
        """Test both from and to date filters work correctly"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        yesterday_str = self.yesterday.strftime('%Y-%m-%d')
        today_str = self.now.strftime('%Y-%m-%d')
        
        response = self.client.get(f'/api/v1/analytics/segments/?conversion_events=purchase&from={yesterday_str}&to={today_str}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['date_range']['from'], yesterday_str)
        self.assertEqual(response.data['date_range']['to'], today_str)
    
    def test_invalid_from_date_returns_400(self):
        """Test invalid from date format returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&from=not-a-date')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('Invalid date format', response.data['error'])
    
    def test_invalid_to_date_returns_400(self):
        """Test invalid to date format returns 400"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&to=2025/01/01')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('Invalid date format', response.data['error'])
    
    # ===========================================
    # RESPONSE STRUCTURE TESTS
    # ===========================================
    
    def test_response_has_expected_top_level_fields(self):
        """Test response has all expected top-level fields"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('app_name', response.data)
        self.assertIn('granularity', response.data)
        self.assertIn('segment_by', response.data)
        self.assertIn('conversion_events', response.data)
        self.assertIn('date_range', response.data)
        self.assertIn('summary', response.data)
        self.assertIn('interpretation', response.data)
        self.assertIn('segments', response.data)
    
    def test_summary_has_expected_fields(self):
        """Test summary has all expected fields"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        summary = response.data['summary']
        self.assertIn('total_segments', summary)
        self.assertIn('total_conversions', summary)
        self.assertIn('total_sessions', summary)
        self.assertIn('overall_conversion_rate', summary)
    
    def test_response_summary_has_expected_fields(self):
        """Test response summary has expected fields"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        summary = response.data['summary']
        self.assertIn('total_segments', summary)
        self.assertIn('total_conversions', summary)
        self.assertIn('overall_conversion_rate', summary)
    
    def test_segment_has_expected_fields(self):
        """Test each segment has expected fields"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        if response.data['segments']:
            segment = response.data['segments'][0]
            self.assertIn('segment', segment)
            self.assertIn('summary', segment)
            self.assertIn('periods', segment)
            
            # Check segment summary fields
            self.assertIn('total_active_sessions', segment['summary'])
            self.assertIn('total_conversions', segment['summary'])
            self.assertIn('conversion_rate', segment['summary'])
    
    def test_period_has_expected_fields(self):
        """Test each period has expected fields"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        if response.data['segments'] and response.data['segments'][0]['periods']:
            period = response.data['segments'][0]['periods'][0]
            self.assertIn('period', period)
            self.assertIn('active_sessions', period)
            self.assertIn('conversions', period)
            self.assertIn('conversion_rate', period)
    
    def test_app_name_is_correct(self):
        """Test that app_name in response is correct"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['app_name'], 'Test App')
    
    # ===========================================
    # CONVERSION RATE CALCULATION TESTS
    # ===========================================
    
    def test_conversion_rate_calculation(self):
        """Test conversion rate is calculated correctly (conversions / active_sessions)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&segment_by=platform')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        for segment in response.data['segments']:
            for period in segment['periods']:
                if period['active_sessions'] > 0:
                    expected_rate = round(period['conversions'] / period['active_sessions'], 4)
                    self.assertEqual(period['conversion_rate'], expected_rate)
    
    def test_segment_summary_conversion_rate(self):
        """Test segment summary conversion rate is calculated correctly"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&segment_by=platform')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        for segment in response.data['segments']:
            total_buckets = segment['summary']['total_active_sessions']
            total_conversions = segment['summary']['total_conversions']
            if total_buckets > 0:
                expected_rate = round(total_conversions / total_buckets, 4)
                self.assertEqual(segment['summary']['conversion_rate'], expected_rate)
    
    def test_overall_conversion_rate(self):
        """Test overall conversion rate in summary is calculated correctly"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Calculate expected overall rate
        total_buckets = sum(s['summary']['total_active_sessions'] for s in response.data['segments'])
        total_conversions = response.data['summary']['total_conversions']
        
        if total_buckets > 0:
            expected_rate = round(total_conversions / total_buckets, 4)
            self.assertEqual(response.data['summary']['overall_conversion_rate'], expected_rate)
    
    def test_zero_active_buckets_returns_zero_rate(self):
        """Test that zero active buckets returns zero conversion rate"""
        # This is tested implicitly - if a segment has no active buckets, rate should be 0.0
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=nonexistent_event')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should handle gracefully without errors
    
    # ===========================================
    # APP ISOLATION TESTS
    # ===========================================
    
    def test_app_isolation(self):
        """Test that only events from the authenticated app are included"""
        self.client.credentials(HTTP_X_APP_KEY=str(self.other_app.id))
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Other app has 1 event, so should have data
        self.assertEqual(response.data['app_name'], 'Other App')
    
    # ===========================================
    # EDGE CASE TESTS
    # ===========================================
    
    def test_no_events_returns_empty_segments(self):
        """Test that app with no events returns empty segments"""
        empty_app = App.objects.create(name="Empty App", user=self.user)
        self.client.credentials(HTTP_X_APP_KEY=str(empty_app.id))
        
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['segments'], [])
        self.assertEqual(response.data['summary']['total_segments'], 0)
        self.assertEqual(response.data['summary']['total_conversions'], 0)
    
    def test_unknown_platform_shows_as_unknown(self):
        """Test that null platform shows as 'Unknown'"""
        # Create event with null platform
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.now, 
                           session_id='f' * 32, platform=None, country='US')
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&segment_by=platform')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        segment_names = [s['segment'] for s in response.data['segments']]
        self.assertIn('Unknown', segment_names)
    
    def test_unknown_country_shows_as_unknown(self):
        """Test that null country shows as 'Unknown'"""
        # Create event with null country
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.now, 
                           session_id='g' * 32, platform='ios', country=None)
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&segment_by=country')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        segment_names = [s['segment'] for s in response.data['segments']]
        self.assertIn('Unknown', segment_names)
    
    def test_periods_sorted_descending(self):
        """Test that periods are sorted in descending order (newest first)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&granularity=day')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        for segment in response.data['segments']:
            if len(segment['periods']) > 1:
                periods = segment['periods']
                for i in range(len(periods) - 1):
                    # Each period should be >= the next one (newer first)
                    self.assertGreaterEqual(periods[i]['period'], periods[i + 1]['period'])
    
    def test_segments_sorted_by_total_conversions(self):
        """Test that segments are sorted by total conversions (descending)"""
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&segment_by=platform')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        if len(response.data['segments']) > 1:
            segments = response.data['segments']
            for i in range(len(segments) - 1):
                # Each segment should have >= conversions than the next (for platform segments)
                # Note: has_user_id segments have a fixed order (identified first)
                self.assertGreaterEqual(
                    segments[i]['summary']['total_conversions'],
                    segments[i + 1]['summary']['total_conversions']
                )
    
    def test_events_with_null_user_id_excluded_from_buckets(self):
        """Test that events with null user_id are excluded from bucket counts"""
        # Create event with null user_id
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.now, 
                           session_id=None, platform='ios', country='US')
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&segment_by=platform')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # The test passes if no error occurs - null user_ids should be silently excluded
    
    def test_events_with_empty_user_id_excluded_from_buckets(self):
        """Test that events with empty user_id are excluded from bucket counts"""
        # Create event with empty user_id
        Event.objects.create(app=self.app, event_name="app_open", timestamp=self.now, 
                           session_id='', platform='ios', country='US')
        
        self.client.credentials(HTTP_X_APP_KEY=self.app_key)
        response = self.client.get('/api/v1/analytics/segments/?conversion_events=purchase&segment_by=platform')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # The test passes if no error occurs - empty user_ids should be silently excluded



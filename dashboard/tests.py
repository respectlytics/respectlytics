from django.contrib.auth.models import User
from django.test import TestCase

from analytics.models import App


class DashboardViewTestCase(TestCase):
    """Test the main dashboard page"""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')

    def test_dashboard_renders_with_apps(self):
        App.objects.create(name="My Test App", user=self.user)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Test App")

    def test_dashboard_renders_with_non_ascii_named_app(self):
        """
        Regression test: an app whose name slugifies to '' (e.g. Korean-only)
        used to crash /dashboard/ with NoReverseMatch on the stats link.
        """
        app = App.objects.create(name="통계앱", user=self.user)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "통계앱")
        self.assertContains(response, f'/dashboard/stats/{app.slug}/')

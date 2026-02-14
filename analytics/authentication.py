from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.core.exceptions import ValidationError
from .models import App


class AppKeyAuthentication(BaseAuthentication):
    """
    Custom authentication class for app_key based authentication.
    
    Clients must provide an app_key in one of these ways:
    1. HTTP Header: X-App-Key: <uuid>
    2. Query Parameter: ?app_key=<uuid>
    3. Request Body: {"app_key": "<uuid>", ...}
    """
    
    def authenticate(self, request):
        # Try to get app_key from different sources
        app_key = None
        
        # 1. Check HTTP header
        app_key = request.headers.get('X-App-Key')
        
        # 2. Check query parameters
        if not app_key:
            app_key = request.query_params.get('app_key')
        
        # 3. Check request body (for POST requests)
        if not app_key and request.method in ['POST', 'PUT', 'PATCH']:
            app_key = request.data.get('app_key')
        
        # If no app_key provided, return None (anonymous user)
        if not app_key:
            return None
        
        # Try to find the app
        try:
            app = App.objects.get(id=app_key)
            # Return (user, auth) tuple - we use app as the "user"
            return (app, app_key)
        except (App.DoesNotExist, ValueError, ValidationError):
            # ValueError: invalid UUID format
            # ValidationError: from Django UUID field
            raise AuthenticationFailed('Invalid app_key')
    
    def authenticate_header(self, request):
        """
        Return the WWW-Authenticate header value for 401 responses.
        """
        return 'X-App-Key'

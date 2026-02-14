from rest_framework.permissions import BasePermission
from .models import App


class HasValidAppKey(BasePermission):
    """
    Custom permission to require a valid app_key for protected endpoints.
    """
    
    message = 'Valid app_key is required to access this endpoint.'
    
    def has_permission(self, request, view):
        # Check if user is authenticated (has valid app_key)
        return request.user and isinstance(request.user, App)


class IsAuthenticatedOrReadOnly(BasePermission):
    """
    Allow read-only access to unauthenticated users,
    but require authentication for write operations.
    """
    
    def has_permission(self, request, view):
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        return request.user and isinstance(request.user, App)

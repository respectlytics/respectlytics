"""
Shared decorators for the Respectlytics project.
"""
from functools import wraps
from django.http import Http404


def staff_or_404(view_func):
    """
    Decorator that returns 404 for non-staff users instead of redirecting to login.
    This hides the existence of these pages from unauthorized users.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            raise Http404()
        return view_func(request, *args, **kwargs)
    return wrapper

import re


class SanitizeRequestPathMiddleware:
    """
    Middleware to sanitize app_key from request.path_info before logging.
    This ensures that even Django's development server logs show truncated keys.
    """
    
    APP_KEY_PATTERN = re.compile(
        r'([?&]app_key=)([a-f0-9]{8})-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}',
        re.IGNORECASE
    )
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Sanitize the request path for logging
        original_path = request.get_full_path()
        
        if '?app_key=' in original_path or '&app_key=' in original_path:
            sanitized_path = self.APP_KEY_PATTERN.sub(r'\g<1>\g<2>...', original_path)
            # Override the path_info for logging purposes
            request.META['QUERY_STRING'] = sanitized_path.split('?', 1)[1] if '?' in sanitized_path else ''
        
        response = self.get_response(request)
        return response

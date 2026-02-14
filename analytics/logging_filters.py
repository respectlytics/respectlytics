import logging
import re


class SanitizeAppKeyFilter(logging.Filter):
    """
    Logging filter to sanitize app_key from log messages.
    Replaces full app_key values with truncated versions for security.
    
    Works by modifying the formatted output string directly.
    """
    
    # Pattern to match app_key= followed by a UUID
    APP_KEY_PATTERN = re.compile(
        r'([?&]app_key=)([a-f0-9]{8})-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}',
        re.IGNORECASE
    )
    
    def filter(self, record):
        """
        Sanitize the log record by modifying the message after formatting.
        """
        # Create a wrapper around getMessage that sanitizes the output
        original_get_message = record.getMessage
        
        def sanitized_get_message():
            try:
                message = original_get_message()
                return self.sanitize_text(message)
            except Exception:
                return original_get_message()
        
        record.getMessage = sanitized_get_message
        
        # Also sanitize msg and args if they're strings
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = self.sanitize_text(record.msg)
        
        if hasattr(record, 'args') and record.args:
            if isinstance(record.args, (tuple, list)):
                record.args = tuple(
                    self.sanitize_text(arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )
        
        return True
    
    def sanitize_text(self, text):
        """Replace app_key UUIDs with truncated versions."""
        if not text or not isinstance(text, str):
            return text
        
        def replace_key(match):
            prefix = match.group(1)  # ?app_key= or &app_key=
            first_8 = match.group(2)  # First 8 chars
            return f'{prefix}{first_8}...'
        
        return self.APP_KEY_PATTERN.sub(replace_key, text)

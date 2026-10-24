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
        r"([?&]app_key=)([a-f0-9]{8})-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
        re.IGNORECASE,
    )

    SECRET_KEY_PATTERN = re.compile(r"(rl_secret_[A-Za-z0-9]{4})[A-Za-z0-9]{36}")

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
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = self.sanitize_text(record.msg)

        if hasattr(record, "args") and record.args:
            if isinstance(record.args, (tuple, list)):
                record.args = tuple(
                    self.sanitize_text(arg) if isinstance(arg, str) else arg for arg in record.args
                )

        return True

    def sanitize_text(self, text):
        """Replace app_key UUIDs with truncated versions."""
        if not text or not isinstance(text, str):
            return text

        def replace_key(match):
            prefix = match.group(1)  # ?app_key= or &app_key=
            first_8 = match.group(2)  # First 8 chars
            return f"{prefix}{first_8}..."

        text = self.APP_KEY_PATTERN.sub(replace_key, text)
        # A secret key (analytics.models.SecretKey) keeps only the part the account page shows.
        return self.SECRET_KEY_PATTERN.sub(r"\1...", text)


def _code(kind: str, value: str) -> str:
    """A short keyed code for a value: the same value always gives the same code, so events can
    still be followed, but the value cannot be read back from it."""
    import hashlib
    import hmac

    from django.conf import settings

    digest = hmac.new(
        settings.SECRET_KEY.encode(), f"log-{kind}|{value.lower()}".encode(), hashlib.sha256
    ).hexdigest()
    return f"{kind}:{digest[:10]}"


class RedactPersonalDataFilter(logging.Filter):
    """No email or IP address reaches respectlytics.com's log (core/settings.py, LOGGING).

    The server keeps the log in files rotated by size, not by age, so a line could outlive any
    period the privacy policy could promise. Each address in a line becomes a keyed code
    (email:..., ip:...) before it is written, wherever in the code the line was made, so one
    filter keeps every present and future log line in line with the policy.
    """

    EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
    # Candidates only: each is checked to be an address before it is replaced, so a time such
    # as 21:32:17 or a version number stays as it is.
    IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
    IPV6 = re.compile(r"(?<![\w:.])[0-9a-fA-F]{0,4}(?::[0-9a-fA-F]{0,4}){2,7}(?![\w:])")

    @classmethod
    def redact(cls, text: str) -> str:
        import ipaddress

        def address(match):
            try:
                ipaddress.ip_address(match.group(0))
            except ValueError:
                return match.group(0)
            return _code("ip", match.group(0))

        text = cls.EMAIL.sub(lambda m: _code("email", m.group(0)), text)
        text = cls.IPV4.sub(address, text)
        return cls.IPV6.sub(address, text)

    def filter(self, record):
        try:
            record.msg = self.redact(record.getMessage())
            record.args = ()
        except Exception:
            record.msg, record.args = "[a log line that could not be checked for addresses]", ()
        return True

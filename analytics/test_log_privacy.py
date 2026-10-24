"""No email or IP address reaches respectlytics.com's log or its error mails (privacy policy,
3.5): analytics/logging_filters.py and analytics/error_reports.py."""

import io
import logging
import sys
from unittest import skipIf

from django.conf import settings
from django.contrib.auth.models import User
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.views.debug import get_exception_reporter_class

from .logging_filters import RedactPersonalDataFilter

EMAIL = "someone@example.com"
IPV4 = "198.51.100.23"
IPV6 = "2001:db8::17"
PROXY = "10.244.0.7"
COOKIE = "the-session-cookie"
BROWSER = "Telltale/1.0"


def failed_request(user):
    """A request carrying every kind of personal data a report could pick up."""
    request = RequestFactory().post(
        "/login/",
        {"username": EMAIL, "password": "typed-password"},
        REMOTE_ADDR=PROXY,
        HTTP_CF_CONNECTING_IP=IPV4,
        HTTP_X_FORWARDED_FOR=IPV6,
        HTTP_USER_AGENT=f"Mozilla/5.0 (Macintosh) {BROWSER}",
        HTTP_COOKIE=f"sessionid={COOKIE}",
    )
    request.user = user
    return request


def fail():
    # The report shows the source lines around each frame, so none of the values above is
    # written near this one.
    raise RuntimeError("boom")


COMMUNITY = getattr(settings, "RESPECTLYTICS_EDITION", None) == "community"


class RedactTest(SimpleTestCase):
    def test_emails_and_addresses_become_codes(self):
        text = RedactPersonalDataFilter.redact(f"login by {EMAIL} from {IPV4} and [{IPV6}]")
        for value in (EMAIL, IPV4, IPV6):
            self.assertNotIn(value, text)
        self.assertRegex(text, r"email:[0-9a-f]{10}.*ip:[0-9a-f]{10}.*ip:[0-9a-f]{10}")

    def test_the_same_address_always_gives_the_same_code(self):
        first, second = (RedactPersonalDataFilter.redact(f"from {IPV4}") for _ in range(2))
        self.assertEqual(first, second)

    def test_times_versions_and_ids_stay_as_they_are(self):
        line = "21:32:17 Django 6.1.2 app 70e1b62e-6cbb-4b16-a3a9-fd6c444c8a3e GET /api/v1/x"
        self.assertEqual(RedactPersonalDataFilter.redact(line), line)


@skipIf(COMMUNITY, "respectlytics.com's log settings")
class ConfiguredLogTest(SimpleTestCase):
    def test_a_line_written_anywhere_reaches_the_log_without_addresses(self):
        logger = logging.getLogger("analytics")
        [handler] = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)][:1]
        stream, handler.stream = handler.stream, io.StringIO()
        try:
            logger.warning(f"[SECURITY_EVENT] {{'email': '{EMAIL}', 'ip': '{IPV4}'}}")
            written = handler.stream.getvalue()
        finally:
            handler.stream = stream
        self.assertIn("SECURITY_EVENT", written)
        self.assertNotIn(EMAIL, written)
        self.assertNotIn(IPV4, written)


@skipIf(COMMUNITY, "respectlytics.com's error report settings")
class ErrorMailTest(TestCase):
    def test_the_report_of_a_failed_request_carries_no_address_cookie_or_email(self):
        user = User.objects.create_user(EMAIL, EMAIL, "pw-not-used-1")
        request = failed_request(user)
        try:
            fail()
        except RuntimeError:
            reporter = get_exception_reporter_class(request)(request, *sys.exc_info())
        report = reporter.get_traceback_text() + reporter.get_traceback_html()
        self.assertIn("RuntimeError", report)
        self.assertIn(f"user {user.pk}", report)
        found = [v for v in (EMAIL, IPV4, IPV6, PROXY, COOKIE, BROWSER) if v in report]
        self.assertEqual(found, [])

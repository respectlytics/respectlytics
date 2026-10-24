"""Error mails (Django's report of a failed request to ADMINS, core/settings.py).

Django already hides every setting named like a secret; these also keep out the request's
addresses, browser, cookies (a session cookie in a mail is a way into the account), form fields
and the values of local variables, and name a signed-in person by number, since a username here
is an email address.
"""

import re

from django.views.debug import ExceptionReporter, SafeExceptionReporterFilter


class PrivateExceptionReporterFilter(SafeExceptionReporterFilter):
    hidden_settings = re.compile(
        "API|AUTH|TOKEN|KEY|SECRET|PASS|SIGNATURE|ADDR|_IP$|FORWARDED|COOKIE|USER_AGENT",
        flags=re.IGNORECASE,
    )

    def get_post_parameters(self, request):
        if request is None:
            return {}
        return {name: self.cleansed_substitute for name in request.POST}

    def get_traceback_frame_variables(self, request, tb_frame):
        # A variable may hold an email, a user or a request; the traceback's lines say where.
        return [(name, self.cleansed_substitute) for name in tb_frame.f_locals]

    def get_safe_cookies(self, request):
        if request is None:
            return {}
        return {name: self.cleansed_substitute for name in request.COOKIES}


class PrivateExceptionReporter(ExceptionReporter):
    def get_traceback_data(self):
        data = super().get_traceback_data()
        user = getattr(self.request, "user", None) if self.request is not None else None
        if user is not None and getattr(user, "is_authenticated", False):
            data["user_str"] = f"user {user.pk}"
        return data

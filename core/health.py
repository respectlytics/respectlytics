"""The health endpoint the uptime watchdog and the deploy gate read.

It answers {"status": "ok"} after one query and says nothing else, so it can be
public, and it is answered before any ban (analytics/middleware.py), so a ban can
never make the service look down (the loheden-security skill, Client address,
bans and rate limits). A failure is logged on the server, never put in the answer.
"""

import logging

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@never_cache
@require_GET
def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("[HEALTHZ] the database did not answer")
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})

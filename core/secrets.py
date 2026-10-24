"""The one way a secret a customer gives us is kept: encrypted with Fernet under a key derived
from SECRET_KEY, readable under any key in SECRET_KEY_FALLBACKS while SECRET_KEY is rotated
(the loheden-security skill, Secrets). An alert's Slack or webhook address is such a secret:
whoever holds it can post into the customer's channel.

No view ever sees the ciphertext, and no second key exists to lose: the database alone reads
nothing, and a new SECRET_KEY with the old one in the fallbacks keeps everything readable.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings

CONTEXT = b"respectlytics:customer-secret:v1"


def _fernet(secret):
    digest = hashlib.sha256(CONTEXT + secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _keys():
    secrets = [settings.SECRET_KEY, *getattr(settings, "SECRET_KEY_FALLBACKS", [])]
    return MultiFernet([_fernet(s) for s in secrets if s])


def encrypt(value):
    """The text, encrypted; an empty value stays empty."""
    if not value:
        return ""
    return _keys().encrypt(value.encode()).decode()


def decrypt(token):
    """The text again, or "" for an empty or unreadable token (a key that is no longer kept)."""
    if not token:
        return ""
    try:
        return _keys().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""

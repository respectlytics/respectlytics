"""Who is blocked, and the one place a block is made (loheden-security, "Client address, bans").

Three kinds of block, all kept in the database so every gunicorn worker sees them and a deploy
forgets none (analytics/middleware.py and throttling.py decide when):

- An attack signal (a known scanner path, and on respectlytics.com a POST to /admin or a login
  as admin or root) blocks the address for 12 months, renewed each time it tries again.
- A 404 scan (20 different missing pages within 5 minutes) blocks it for 24 hours, then 7 days,
  then 30 days when it comes back.
- Repeated failed API keys (10 within 15 minutes) block it for an hour.

A block keeps a code computed from the address with the site's secret key, never the address
itself, and daily_jobs deletes it 30 days after it ends; the admin finds a block by its address
all the same, by computing the code. respectaso-web's security/blocks.py is the reference.
"""

import hashlib
import hmac
import ipaddress
import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.dispatch import Signal
from django.utils import timezone

from .client_ip import PROXY_NETWORKS

logger = logging.getLogger(__name__)

ATTACK = "attack"
SCAN = "scan"
AUTH = "auth"
KINDS = [(ATTACK, "Attack signal"), (SCAN, "404 scan"), (AUTH, "Failed API keys")]

ATTACK_BLOCK = timedelta(days=365)
SCAN_BLOCKS = (timedelta(hours=24), timedelta(days=7), timedelta(days=30))
AUTH_BLOCK = timedelta(hours=1)
KEEP_AFTER_END = timedelta(days=30)

# Addresses that many unrelated clients share, so a block on one shuts out all of them.
# Cloudflare sends every Worker's request to another site from this one address, whoever runs
# the Worker: a customer sending events from a Worker and any scanner someone runs on Workers
# are the same visitor here. Its bad requests are still refused one at a time, but it is never
# blocked from the whole site: on 2026-10-13 a WordPress scanner got it banned at loheden.com,
# and the uptime watchdog with it.
# https://developers.cloudflare.com/fundamentals/reference/http-headers/
SHARED_ADDRESSES = frozenset({"2a06:98c0:3600::103"})

# Sent robustly, so a receiver's failure never reaches the request. Nothing in the community
# edition listens; respectlytics.com's edge app lists blocked addresses at Cloudflare with them.
#   address_banned(ip, until): a block was made or lengthened.
#   banned_address_refused(ip, until): a blocked address came back and was refused.
#   blocks_lifted(keys): the admin lifted these blocks (their codes).
address_banned = Signal()
banned_address_refused = Signal()
blocks_lifted = Signal()


def address_key(ip: str) -> str:
    """The code a block is filed under: the address, keyed with the secret key, one way."""
    return hmac.new(
        settings.SECRET_KEY.encode(), f"blocked-address|{ip}".encode(), hashlib.sha256
    ).hexdigest()


def blockable(ip) -> bool:
    """False for an address many visitors share, and for the server's own: the deploy's checks
    arrive from loopback, and a private address means a request that never came through the
    edge in front of the site, which a block would land on everyone behind it."""
    try:
        address = ipaddress.ip_address(ip)
    except (TypeError, ValueError):
        return False
    return not (
        str(address) in SHARED_ADDRESSES
        or address.is_loopback
        or address.is_link_local
        or address.is_unspecified
        or any(address in network for network in PROXY_NETWORKS)
    )


def active_block(ip):
    """The block this address is under now, or None. Fails open: a database that cannot be
    read must not take the site down with it."""
    from .models import BlockedAddress

    if not blockable(ip):
        return None
    try:
        return BlockedAddress.objects.filter(
            key=address_key(str(ipaddress.ip_address(ip))), expires_at__gt=timezone.now()
        ).first()
    except Exception:
        logger.warning("[SECURITY] Blocks unreadable, failing open")
        return None


def refused(ip, row) -> None:
    """A blocked visitor came back: tell whoever listens, who may list it again."""
    banned_address_refused.send_robust(sender=refused, ip=ip, until=row.expires_at)


def block(ip, kind: str, reason: str):
    """Block this address, or renew and lengthen the block it already has. Returns the block,
    or None when the address may not be blocked."""
    from .models import BlockedAddress

    if not blockable(ip):
        logger.info("[SECURITY] Not blocking an address many visitors share: %s", reason)
        return None
    ip = str(ipaddress.ip_address(ip))
    now = timezone.now()
    key = address_key(ip)
    first_length = {ATTACK: ATTACK_BLOCK, SCAN: SCAN_BLOCKS[0], AUTH: AUTH_BLOCK}[kind]
    try:
        # Filed by the insert itself, never after a look: two requests from one address that
        # reach two workers at once make one block, and the second renews it.
        with transaction.atomic():
            row = BlockedAddress.objects.create(
                key=key, kind=kind, reason=reason[:200], expires_at=now + first_length
            )
    except IntegrityError:
        existing = BlockedAddress.objects.get(key=key)
        # An attack outranks a scan, and a scan an API-key block: the longest kind stays.
        rank = {ATTACK: 2, SCAN: 1, AUTH: 0}
        kind = max(kind, existing.kind, key=rank.__getitem__)
        if kind == ATTACK:
            length = ATTACK_BLOCK
        elif kind == SCAN:
            length = SCAN_BLOCKS[min(existing.times, len(SCAN_BLOCKS) - 1)]
        else:
            length = AUTH_BLOCK
        BlockedAddress.objects.filter(pk=existing.pk).update(
            kind=kind,
            reason=reason[:200],
            times=F("times") + 1,
            last_blocked=now,
            expires_at=max(existing.expires_at, now + length),
        )
        row = BlockedAddress.objects.get(pk=existing.pk)
    address_banned.send_robust(sender=block, ip=ip, until=row.expires_at)
    # No address in the log: the container log rotates by size, not by age, and could keep it
    # past the 30 days the privacy policy promises.
    logger.warning("[SECURITY] Blocked an address (%s): %s", kind, reason)
    return row


def lift(keys) -> tuple[int, bool]:
    """Lift the blocks filed under these codes (the admin's action): how many were lifted, and
    whether every listener was reached (False when the edge in front could not be told)."""
    from .models import BlockedAddress

    keys = set(keys)
    deleted, _ = BlockedAddress.objects.filter(key__in=keys).delete()
    answers = blocks_lifted.send_robust(sender=lift, keys=keys) if keys else []
    reached = all(answer is not None and not isinstance(answer, Exception) for _, answer in answers)
    return deleted, reached


def delete_ended(now=None) -> int:
    """Blocks that ended more than 30 days ago (daily_jobs)."""
    from .models import BlockedAddress

    now = now or timezone.now()
    deleted, _ = BlockedAddress.objects.filter(expires_at__lt=now - KEEP_AFTER_END).delete()
    return deleted


def block_attack_login(sender, credentials, request=None, **kwargs) -> None:
    """django.contrib.auth's user_login_failed: a login as admin, root or another name nobody
    here uses is an attack signal. Only where settings.ATTACK_USERNAMES names them
    (respectlytics.com): a self-hosted copy may well have an account called admin."""
    names = getattr(settings, "ATTACK_USERNAMES", ())
    username = str(credentials.get("username", "")).strip().lower()
    if request is not None and username in names:
        from .client_ip import get_client_ip

        block(get_client_ip(request), ATTACK, f"login attempt as {username}")

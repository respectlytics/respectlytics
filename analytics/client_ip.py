"""The visitor's address: the one function every part of Respectlytics reads it from.

The bans in analytics/middleware.py and analytics/throttling.py, the per-endpoint
rate limits (django-ratelimit, through RATELIMIT_IP_META_KEY), the country an
event is geolocated to, the security log and the record of a buyer accepting the
terms all read it here, so they can never disagree about who a request came from.

Only a header that the edge in front of the app sets, and overwrites when a
client sends its own, can say who the visitor is. Which headers those are
depends on where the app runs, so settings.TRUSTED_CLIENT_IP_HEADERS names them:

- respectlytics.com runs on DigitalOcean App Platform, whose edge is Cloudflare.
  Cloudflare puts the visitor in CF-Connecting-IP and documents that it
  overwrites any value a client sends, so that header comes first; App
  Platform's do-connecting-ip, of which DigitalOcean says no such thing, is the
  fallback. X-Forwarded-For is no answer there: App Platform fills it
  with its own ingress server, and before that its first entry is whatever the
  client chose to send, so a ban keyed on it could be dodged by changing the
  header, or aimed at anyone else's address.
  https://docs.digitalocean.com/support/where-can-i-find-the-client-ip-address-of-a-request-connecting-to-my-app/
- A self-hosted copy trusts no such header unless its owner names one
  (TRUSTED_CLIENT_IP_HEADER, for a server behind Cloudflare), because without
  that edge in front anyone can send it. Behind the owner's own reverse proxy
  (the nginx setup in the docs) the proxy appends the address it saw to
  X-Forwarded-For. Reading the list from the right, stepping over proxies on
  loopback and private addresses, finds that address, and nothing a client
  writes to the left of it counts.
"""

import ipaddress

from django.conf import settings

# Where a reverse proxy of the server's own sits: the machine itself, or a
# private network such as Docker's. Python's own is_private would also count
# the documentation and other reserved ranges, which are not proxies of ours.
PROXY_NETWORKS = tuple(
    ipaddress.ip_network(n)
    for n in (
        "127.0.0.0/8",
        "::1/128",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
    )
)


def _address(value):
    try:
        return ipaddress.ip_address((value or "").strip())
    except ValueError:
        return None


def _is_proxy(address):
    return any(address in network for network in PROXY_NETWORKS)


def get_client_ip(request) -> str:
    for header in getattr(settings, "TRUSTED_CLIENT_IP_HEADERS", ()):
        address = _address(request.META.get(header))
        if address:
            return str(address)

    address = request.META.get("REMOTE_ADDR", "")
    hops = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
    current = _address(address)
    while current and _is_proxy(current) and hops:
        previous = _address(hops.pop())
        if previous is None:
            break
        current = previous
        address = str(previous)
    return address

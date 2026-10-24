"""
IP geolocation from a database file on our own server.

The file is MaxMind's GeoLite2 City where the operator has a MaxMind key, and otherwise DB-IP's
free IP to Country Lite, which needs no account (`manage.py update_geoip` downloads either; the
community edition's container does it at start). Lookups never leave the server, and only the
country is kept. Each database's licence asks for a credit where its results are shown, which
`credit()` gives (`analytics/templatetags/geoip.py`, on the stats page).
"""

import logging
from pathlib import Path

import geoip2.database
import geoip2.errors

logger = logging.getLogger(__name__)

GEOIP_DIR = Path(__file__).parent.parent / "geoip_data"
MAXMIND_FILE = GEOIP_DIR / "GeoLite2-City.mmdb"
DBIP_FILE = GEOIP_DIR / "dbip-country-lite.mmdb"

# The credit each licence asks for: MaxMind's GeoLite EULA, section 3, and DB-IP's CC BY 4.0
# terms ("a link back to DB-IP.com on pages that display or use results from the database").
CREDITS = {
    MAXMIND_FILE.name: {
        "text": "This product includes GeoLite Data created by MaxMind, available from",
        "link": "https://www.maxmind.com",
        "link_text": "maxmind.com",
    },
    DBIP_FILE.name: {
        "text": "",
        "link": "https://db-ip.com",
        "link_text": "IP Geolocation by DB-IP",
    },
}


def database_path():
    """The database lookups use: MaxMind's when it is there, else DB-IP's, else None."""
    for path in (MAXMIND_FILE, DBIP_FILE):
        if path.exists():
            return path
    return None


def credit():
    """The credit the database in use asks for, or None when there is none."""
    path = database_path()
    return CREDITS[path.name] if path else None


# Log database status at module load
if database_path():
    logger.info(f"GeoIP database found at {database_path()}")
else:
    logger.warning(f"No GeoIP database in {GEOIP_DIR} - geolocation will be disabled")


def get_location_from_ip(ip_address: str) -> tuple[str | None, str | None]:
    """
    Extract country and region from an IP address, in the database `database_path()` names.
    A country database (DB-IP's) has no region.

    Args:
        ip_address: IPv4 or IPv6 address as a string

    Returns:
        Tuple of (country_code, region_name) or (None, None) if lookup fails

    Examples:
        >>> get_location_from_ip("8.8.8.8")
        ('US', 'California')
        >>> get_location_from_ip("invalid")
        (None, None)
    """
    # Skip localhost and private IPs
    if not ip_address or ip_address in ["127.0.0.1", "localhost", "::1"]:
        return (None, None)

    path = database_path()
    if not path:
        logger.debug(f"No GeoIP database in {GEOIP_DIR}. Geolocation disabled.")
        return (None, None)

    try:
        with geoip2.database.Reader(str(path)) as reader:
            # geoip2 asks for the lookup that matches the file: city() for MaxMind's City,
            # country() for DB-IP's Country Lite, whose answers have no subdivisions.
            if "City" in reader.metadata().database_type:
                response = reader.city(ip_address)
            else:
                response = reader.country(ip_address)

            # Extract country code (2-letter ISO code)
            country = response.country.iso_code if response.country.iso_code else None

            # Extract region/state name
            # subdivisions[0] is the largest subdivision (state/province)
            region = None
            subdivisions = getattr(response, "subdivisions", None)
            if subdivisions and subdivisions.most_specific.name:
                region = subdivisions.most_specific.name

            return (country, region)

    except geoip2.errors.AddressNotFoundError:
        logger.debug("IP address not found in GeoIP database")
        return (None, None)
    except Exception as e:
        logger.error(f"GeoIP lookup error: {e}")
        return (None, None)

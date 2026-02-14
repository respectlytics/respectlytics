"""
IP Geolocation utility using MaxMind GeoLite2.

This module provides automatic geolocation detection from IP addresses
while respecting privacy. It falls back gracefully if the database is unavailable.
"""
import logging
import geoip2.database
import geoip2.errors
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Path to GeoLite2 City database
GEOIP_DB_PATH = Path(__file__).parent.parent / 'geoip_data' / 'GeoLite2-City.mmdb'

# Log database status at module load
if GEOIP_DB_PATH.exists():
    logger.info(f"GeoIP database found at {GEOIP_DB_PATH}")
else:
    logger.warning(f"GeoIP database NOT FOUND at {GEOIP_DB_PATH} - geolocation will be disabled")


def get_location_from_ip(ip_address: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract country and region from an IP address using MaxMind GeoLite2.
    
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
    if not ip_address or ip_address in ['127.0.0.1', 'localhost', '::1']:
        return (None, None)
    
    # Check if database exists
    if not GEOIP_DB_PATH.exists():
        logger.debug(f"GeoIP database not found at {GEOIP_DB_PATH}. Geolocation disabled.")
        return (None, None)
    
    try:
        with geoip2.database.Reader(str(GEOIP_DB_PATH)) as reader:
            response = reader.city(ip_address)
            
            # Extract country code (2-letter ISO code)
            country = response.country.iso_code if response.country.iso_code else None
            
            # Extract region/state name
            # subdivisions[0] is the largest subdivision (state/province)
            region = None
            if response.subdivisions.most_specific.name:
                region = response.subdivisions.most_specific.name
            
            return (country, region)
            
    except geoip2.errors.AddressNotFoundError:
        logger.debug("IP address not found in GeoIP database")
        return (None, None)
    except Exception as e:
        logger.error(f"GeoIP lookup error: {e}")
        return (None, None)


def get_client_ip(request) -> str:
    """
    Extract the real client IP address from the request.
    
    Handles proxies, load balancers, and X-Forwarded-For headers.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        Client IP address as a string
    """
    # Check X-Forwarded-For header (used by proxies/load balancers)
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # Take the first IP in the chain (the original client)
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        # Fall back to REMOTE_ADDR
        ip = request.META.get('REMOTE_ADDR', '')
    
    return ip

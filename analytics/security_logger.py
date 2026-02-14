"""
SEC-010: Structured Security Event Logger

Provides a unified interface for logging security-related events with
structured data for easy parsing and analysis.

Usage:
    from analytics.security_logger import log_security_event, SecurityEvent
    
    log_security_event(
        SecurityEvent.LOGIN_FAILURE,
        ip='192.168.1.1',
        email='user@example.com',
        user_agent='Mozilla/5.0...',
        reason='Invalid password'
    )
"""

import json
import logging
from datetime import datetime
from typing import Optional

# Use the analytics logger which writes to security.log
logger = logging.getLogger('analytics')


class SecurityEvent:
    """Security event type constants for consistent logging."""
    
    # Authentication events
    LOGIN_SUCCESS = 'login_success'
    LOGIN_FAILURE = 'login_failure'
    LOGOUT = 'logout'
    
    # Account security events
    ACCOUNT_LOCKED = 'account_locked'
    ACCOUNT_UNLOCKED = 'account_unlocked'
    PASSWORD_CHANGED = 'password_changed'
    PASSWORD_RESET_REQUESTED = 'password_reset_requested'
    PASSWORD_RESET_COMPLETED = 'password_reset_completed'
    
    # Registration events
    REGISTRATION_STARTED = 'registration_started'
    REGISTRATION_COMPLETED = 'registration_completed'
    EMAIL_VERIFIED = 'email_verified'
    VERIFICATION_RESENT = 'verification_resent'
    
    # Rate limiting & banning events
    RATE_LIMITED = 'rate_limited'
    IP_BANNED = 'ip_banned'
    IP_UNBANNED = 'ip_unbanned'
    
    # Attack detection events
    ATTACK_PATH_PROBE = 'attack_path_probe'
    PATH_SCAN_DETECTED = 'path_scan_detected'
    
    # API security events
    API_AUTH_FAILURE = 'api_auth_failure'
    INVALID_APP_KEY = 'invalid_app_key'
    
    # Data management events
    DATA_DELETION = 'data_deletion'


def log_security_event(
    event_type: str,
    ip: Optional[str] = None,
    email: Optional[str] = None,
    user_id: Optional[int] = None,
    user_agent: Optional[str] = None,
    path: Optional[str] = None,
    reason: Optional[str] = None,
    severity: str = 'INFO',
    **extra
) -> None:
    """
    Log a structured security event.
    
    Args:
        event_type: One of SecurityEvent constants
        ip: Client IP address
        email: User email (if known)
        user_id: User ID (if authenticated)
        user_agent: Browser/client user agent
        path: Request path (for attack detection)
        reason: Human-readable reason for event
        severity: Log level - 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
        **extra: Additional context-specific data
    
    Example:
        log_security_event(
            SecurityEvent.LOGIN_FAILURE,
            ip='192.168.1.1',
            email='user@example.com',
            reason='Invalid password',
            attempt_count=3
        )
    """
    # Build structured event data
    event_data = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'event': event_type,
    }
    
    # Add optional fields only if provided
    if ip:
        event_data['ip'] = ip
    if email:
        event_data['email'] = email
    if user_id:
        event_data['user_id'] = user_id
    if user_agent:
        # Truncate long user agents
        event_data['user_agent'] = user_agent[:200] if len(user_agent) > 200 else user_agent
    if path:
        event_data['path'] = path
    if reason:
        event_data['reason'] = reason
    
    # Add any extra fields
    event_data.update(extra)
    
    # Format as JSON for easy parsing
    json_message = json.dumps(event_data, default=str)
    
    # Log with appropriate level
    level = getattr(logging, severity.upper(), logging.INFO)
    logger.log(level, f"[SECURITY_EVENT] {json_message}")


def get_client_info(request) -> dict:
    """
    Extract client information from Django request for logging.
    
    Returns:
        dict with ip, user_agent, and path
    """
    from analytics.middleware import get_client_ip
    
    return {
        'ip': get_client_ip(request),
        'user_agent': request.META.get('HTTP_USER_AGENT', '')[:200],
        'path': request.path,
    }

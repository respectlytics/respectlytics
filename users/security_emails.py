"""
SEC-007: Security Alert Emails

Email notifications for security events:
1. Account lockout alert (to admin) - when account is locked
2. Password changed notification (to user) - after password change
3. Failed login warning (to user) - after suspicious activity

All emails use HTML templates with plain text fallbacks.
Uses same base template and styling as billing emails.

Rate limiting (SEC-007b):
- Failed login warnings: Max 3 per user per day
- Lockout alerts to admin: Max 10 per day total
"""

import logging
from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger('analytics')

# Admin email for security alerts (from instructions)
ADMIN_EMAIL = 'respectlytics@loheden.com'

# Base URL for links in emails
BASE_URL = 'https://respectlytics.com'

# Rate limiting settings (SEC-007b)
MAX_LOGIN_WARNINGS_PER_USER_PER_DAY = 3
MAX_LOCKOUT_ALERTS_PER_DAY = 10
RATE_LIMIT_WINDOW = 86400  # 24 hours in seconds


def _get_common_context():
    """Get common context for all security email templates."""
    return {
        'year': timezone.now().year,
        'base_url': BASE_URL,
        'support_email': ADMIN_EMAIL,
        'dashboard_url': f'{BASE_URL}/dashboard/',
        'password_reset_url': f'{BASE_URL}/password-reset/',
        'preferences_url': f'{BASE_URL}/account/preferences/',
    }


def _check_rate_limit(cache_key, max_count):
    """
    Check if rate limit is exceeded and increment counter.
    
    Args:
        cache_key: Unique key for this rate limit
        max_count: Maximum allowed emails in the window
    
    Returns:
        bool: True if email can be sent, False if rate limited
    """
    current_count = cache.get(cache_key, 0)
    if current_count >= max_count:
        return False
    cache.set(cache_key, current_count + 1, RATE_LIMIT_WINDOW)
    return True


def _send_security_email(to_email, subject, html_template, text_template, context, is_admin=False):
    """
    Send a security email with HTML and plain text versions.
    
    Args:
        to_email: Recipient email address
        subject: Email subject line
        html_template: Path to HTML template
        text_template: Path to plain text template
        context: Template context dict
        is_admin: If True, this is an admin alert (always send)
    
    Returns:
        bool: True if email sent successfully
    """
    try:
        # Merge common context
        full_context = _get_common_context()
        full_context.update(context)
        
        # Render templates
        html_content = render_to_string(html_template, full_context)
        text_content = render_to_string(text_template, full_context)
        
        # Create email with reply-to header
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
            reply_to=[settings.EMAIL_REPLY_TO],
        )
        email.attach_alternative(html_content, 'text/html')
        
        # Send
        email.send(fail_silently=False)
        
        log_prefix = '[SECURITY_EMAIL]' if is_admin else '[EMAIL]'
        logger.info(f'{log_prefix} Sent "{subject}" to {to_email}')
        return True
        
    except Exception as e:
        logger.error(f'[SECURITY_EMAIL] Failed to send "{subject}" to {to_email}: {e}')
        return False


# =============================================================================
# Admin Security Alerts
# =============================================================================

def send_account_lockout_alert(user_email, ip_address, attempt_count):
    """
    Notify admin when an account is locked due to failed login attempts.
    
    SEC-003/SEC-007: Sent when account lockout is triggered.
    SEC-007b: Rate limited to 10 emails per day to prevent inbox flooding.
    
    Args:
        user_email: Email of the locked account
        ip_address: IP address of the last failed attempt
        attempt_count: Number of failed attempts
    
    Returns:
        bool: True if email sent, False if rate limited or failed
    """
    # SEC-007b: Rate limit admin lockout alerts
    cache_key = 'security_email:lockout_alerts_today'
    if not _check_rate_limit(cache_key, MAX_LOCKOUT_ALERTS_PER_DAY):
        logger.warning(f'[SECURITY_EMAIL] Rate limited: lockout alert for {user_email} (max {MAX_LOCKOUT_ALERTS_PER_DAY}/day)')
        return False
    
    subject = f'🚨 Account Locked: {user_email}'
    
    context = {
        'email': user_email,
        'ip_address': ip_address,
        'attempt_count': attempt_count,
        'lockout_duration': '30 minutes',
        'timestamp': timezone.now(),
    }
    
    return _send_security_email(
        to_email=ADMIN_EMAIL,
        subject=subject,
        html_template='emails/security/account_lockout_admin.html',
        text_template='emails/security/account_lockout_admin.txt',
        context=context,
        is_admin=True
    )


def send_ip_banned_alert(ip_address, reason, details=None):
    """
    Notify admin when an IP is banned.
    
    SEC-013/SEC-007: Sent when IP is banned for 404 scanning or attack paths.
    
    Args:
        ip_address: The banned IP address
        reason: Why the IP was banned (e.g., 'excessive_404s', 'attack_path')
        details: Additional context (e.g., the attack path)
    """
    subject = f'🛡️ IP Banned: {ip_address}'
    
    context = {
        'ip_address': ip_address,
        'reason': reason,
        'details': details,
        'ban_duration': '1 hour',
        'timestamp': timezone.now(),
    }
    
    return _send_security_email(
        to_email=ADMIN_EMAIL,
        subject=subject,
        html_template='emails/security/ip_banned_admin.html',
        text_template='emails/security/ip_banned_admin.txt',
        context=context,
        is_admin=True
    )


# =============================================================================
# User Security Notifications
# =============================================================================

def send_password_changed_notification(user):
    """
    Notify user when their password is changed.
    
    This is a transactional email - always sent regardless of preferences.
    
    Args:
        user: Django User object
    """
    subject = 'Your Respectlytics password was changed'
    
    context = {
        'user': user,
        'timestamp': timezone.now(),
    }
    
    return _send_security_email(
        to_email=user.email,
        subject=subject,
        html_template='emails/security/password_changed.html',
        text_template='emails/security/password_changed.txt',
        context=context,
        is_admin=False
    )


def send_failed_login_warning(user, attempt_count, ip_address):
    """
    Notify user of suspicious login activity on their account.
    
    Sent after 3 failed attempts (before lockout at 5).
    This is a transactional security email - always sent.
    
    SEC-007b: Rate limited to 3 emails per user per day to prevent inbox flooding.
    
    Args:
        user: Django User object
        attempt_count: Number of failed attempts
        ip_address: IP address of the attempts
    
    Returns:
        bool: True if email sent, False if rate limited or failed
    """
    # SEC-007b: Rate limit per-user login warnings
    cache_key = f'security_email:login_warning:{user.id}'
    if not _check_rate_limit(cache_key, MAX_LOGIN_WARNINGS_PER_USER_PER_DAY):
        logger.warning(f'[SECURITY_EMAIL] Rate limited: login warning for user {user.id} (max {MAX_LOGIN_WARNINGS_PER_USER_PER_DAY}/day)')
        return False
    
    subject = '⚠️ Suspicious login activity on your Respectlytics account'
    
    context = {
        'user': user,
        'attempt_count': attempt_count,
        'ip_address': ip_address,
        'timestamp': timezone.now(),
    }
    
    return _send_security_email(
        to_email=user.email,
        subject=subject,
        html_template='emails/security/failed_login_warning.html',
        text_template='emails/security/failed_login_warning.txt',
        context=context,
        is_admin=False
    )

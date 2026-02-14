"""
SEC-011: Admin Security Dashboard

Provides a security overview dashboard for admin users including:
- Currently banned IPs
- Locked accounts
- Recent security events from logs
- 24-hour security statistics
- Unban/unlock actions
"""

import json
import os
import re
from datetime import datetime, timedelta
from collections import Counter
from typing import List, Dict, Any, Optional

from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.db import connection


User = get_user_model()


# =============================================================================
# Cache Key Patterns
# =============================================================================

# These patterns match the cache keys used by our security middleware
BANNED_IP_PATTERN = 'banned:'        # banned:{ip}
LOCKED_ACCOUNT_PATTERN = 'account_locked:'  # account_locked:{email}
LOGIN_ATTEMPTS_PATTERN = 'login_attempts:'  # login_attempts:{email}
FAILED_AUTH_PATTERN = 'failed_auth:'  # failed_auth:{ip}
SCAN_404_PATTERN = '404_scan:'       # 404_scan:{ip}


def get_banned_ips() -> List[Dict[str, Any]]:
    """
    Get list of currently banned IPs from cache.
    
    Note: Django's database cache doesn't support key scanning,
    so we track banned IPs separately.
    
    Returns:
        List of dicts with 'ip', 'banned_at', 'reason'
    """
    # Try to get tracked banned IPs list
    tracked_ips = cache.get('security:banned_ips_list', [])
    
    # Validate each IP is still actually banned
    valid_banned = []
    for ip_info in tracked_ips:
        ip = ip_info.get('ip')
        if ip and cache.get(f'banned:{ip}'):
            valid_banned.append(ip_info)
    
    # Also check the database cache table directly for banned: keys
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT cache_key, expires 
                FROM django_cache 
                WHERE cache_key LIKE %s 
                AND expires > NOW()
                ORDER BY expires DESC
                LIMIT 100
            """, [f'%banned:%'])
            rows = cursor.fetchall()
            
            # Extract IPs from cache keys (format: :1:banned:192.168.1.100)
            for cache_key, expires in rows:
                # Cache key format: :version:key
                match = re.search(r'banned:([^:]+)$', cache_key)
                if match:
                    ip = match.group(1)
                    # Check if already in list
                    if not any(b['ip'] == ip for b in valid_banned):
                        valid_banned.append({
                            'ip': ip,
                            'expires': expires,
                            'reason': 'Unknown (from cache)'
                        })
    except Exception:
        # Silently fail if direct cache access doesn't work
        pass
    
    return valid_banned


def get_locked_accounts() -> List[Dict[str, Any]]:
    """
    Get list of currently locked accounts from cache.
    
    Returns:
        List of dicts with 'email', 'locked_at', 'attempts'
    """
    locked_accounts = []
    
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT cache_key, expires 
                FROM django_cache 
                WHERE cache_key LIKE %s 
                AND expires > NOW()
                ORDER BY expires DESC
                LIMIT 100
            """, [f'%account_locked:%'])
            rows = cursor.fetchall()
            
            for cache_key, expires in rows:
                # Extract email from cache key
                match = re.search(r'account_locked:([^:]+)$', cache_key)
                if match:
                    email = match.group(1)
                    # Get attempt count if available
                    attempts = cache.get(f'login_attempts:{email}', 0)
                    locked_accounts.append({
                        'email': email,
                        'expires': expires,
                        'attempts': attempts
                    })
    except Exception:
        pass
    
    return locked_accounts


def parse_security_log(limit: int = 100, hours: int = 24) -> List[Dict[str, Any]]:
    """
    Parse recent security events from the security log file.
    
    Args:
        limit: Maximum number of events to return
        hours: Only return events from last N hours
        
    Returns:
        List of security event dicts
    """
    log_path = settings.BASE_DIR / 'logs' / 'security.log'
    events = []
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    if not os.path.exists(log_path):
        return events
    
    # Read log file in reverse (most recent first)
    try:
        with open(log_path, 'r') as f:
            lines = f.readlines()
        
        # Parse lines in reverse order
        for line in reversed(lines):
            if len(events) >= limit:
                break
            
            # Skip non-security lines
            if '[SECURITY' not in line:
                continue
            
            event = _parse_log_line(line)
            if event:
                # Check if within time window
                if event.get('timestamp'):
                    try:
                        event_time = datetime.fromisoformat(event['timestamp'].replace('Z', ''))
                        if event_time < cutoff_time:
                            continue
                    except (ValueError, TypeError):
                        pass
                
                events.append(event)
    except Exception as e:
        events.append({
            'level': 'ERROR',
            'message': f'Error reading log file: {str(e)}',
            'timestamp': datetime.utcnow().isoformat()
        })
    
    return events


def _parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse a single log line into a structured event dict.
    
    Handles both structured JSON events and legacy format.
    """
    # Log format: LEVEL YYYY-MM-DD HH:MM:SS,mmm module [SECURITY...] message
    # Example: WARNING 2025-12-08 14:44:15,478 views [SECURITY] Failed login attempt: test@test.com
    
    match = re.match(
        r'^(INFO|WARNING|ERROR|CRITICAL)\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}),\d+\s+(\w+)\s+(.+)$',
        line.strip()
    )
    
    if not match:
        return None
    
    level, timestamp, module, message = match.groups()
    
    event = {
        'level': level,
        'timestamp': timestamp.replace(' ', 'T'),
        'module': module,
        'raw_message': message
    }
    
    # Try to extract structured JSON from [SECURITY_EVENT] messages
    if '[SECURITY_EVENT]' in message:
        json_match = re.search(r'\[SECURITY_EVENT\]\s*({.+})$', message)
        if json_match:
            try:
                event_data = json.loads(json_match.group(1))
                event.update(event_data)
                event['type'] = 'structured'
            except json.JSONDecodeError:
                pass
    
    # Parse legacy format messages
    elif '[SECURITY]' in message:
        event['type'] = 'legacy'
        
        # Extract common patterns
        if 'Failed login attempt' in message:
            event['event'] = 'login_failure'
            email_match = re.search(r':\s*(\S+@\S+)', message)
            if email_match:
                event['email'] = email_match.group(1)
                
        elif 'Login rate limited' in message:
            event['event'] = 'rate_limited'
            ip_match = re.search(r'IP:\s*([^\s,]+)', message)
            if ip_match:
                event['ip'] = ip_match.group(1)
                
        elif 'banned' in message.lower():
            if 'attack path' in message.lower():
                event['event'] = 'ip_banned_attack'
            elif '404' in message:
                event['event'] = 'ip_banned_404'
            else:
                event['event'] = 'ip_banned'
            ip_match = re.search(r'IP\s*([^\s:]+)', message)
            if ip_match:
                event['ip'] = ip_match.group(1)
                
        elif 'Blocked' in message:
            event['event'] = 'blocked'
            ip_match = re.search(r'from\s+([^\s:]+)', message)
            if ip_match:
                event['ip'] = ip_match.group(1)
                
        elif '404 attempt' in message:
            event['event'] = '404_tracking'
            ip_match = re.search(r'from\s+([^\s:]+)', message)
            if ip_match:
                event['ip'] = ip_match.group(1)
                
        elif 'Account locked' in message:
            event['event'] = 'account_locked'
            email_match = re.search(r':\s*(\S+@\S+)', message)
            if email_match:
                event['email'] = email_match.group(1)
    
    return event


def get_security_stats(hours: int = 24) -> Dict[str, Any]:
    """
    Calculate security statistics for the last N hours.
    
    Returns:
        Dict with counts of various security events
    """
    events = parse_security_log(limit=1000, hours=hours)
    
    event_counts = Counter()
    unique_ips = set()
    unique_emails = set()
    
    for event in events:
        event_type = event.get('event', 'other')
        event_counts[event_type] += 1
        
        if event.get('ip'):
            unique_ips.add(event['ip'])
        if event.get('email'):
            unique_emails.add(event['email'])
    
    return {
        'total_events': len(events),
        'login_failures': event_counts.get('login_failure', 0),
        'rate_limited': event_counts.get('rate_limited', 0),
        'ips_banned': event_counts.get('ip_banned', 0) + event_counts.get('ip_banned_attack', 0) + event_counts.get('ip_banned_404', 0),
        'blocked_requests': event_counts.get('blocked', 0),
        'accounts_locked': event_counts.get('account_locked', 0),
        'attack_path_probes': event_counts.get('ip_banned_attack', 0),
        'path_scanning': event_counts.get('404_tracking', 0),
        'unique_ips': len(unique_ips),
        'unique_emails': len(unique_emails),
        'event_counts': dict(event_counts),
        'hours': hours
    }


def unban_ip(ip: str) -> bool:
    """
    Remove an IP from the ban list.
    
    Returns:
        True if successfully unbanned, False otherwise
    """
    try:
        cache.delete(f'banned:{ip}')
        cache.delete(f'failed_auth:{ip}')
        cache.delete(f'404_scan:{ip}')
        
        # Also remove from tracked list
        tracked_ips = cache.get('security:banned_ips_list', [])
        tracked_ips = [b for b in tracked_ips if b.get('ip') != ip]
        cache.set('security:banned_ips_list', tracked_ips, 86400)
        
        return True
    except Exception:
        return False


def unlock_account(email: str) -> bool:
    """
    Unlock a locked account.
    
    Returns:
        True if successfully unlocked, False otherwise
    """
    try:
        email_lower = email.lower()
        cache.delete(f'account_locked:{email_lower}')
        cache.delete(f'login_attempts:{email_lower}')
        return True
    except Exception:
        return False


def track_banned_ip(ip: str, reason: str) -> None:
    """
    Add a banned IP to the tracked list for dashboard display.
    
    Call this when banning an IP to ensure it shows in the dashboard.
    """
    tracked_ips = cache.get('security:banned_ips_list', [])
    
    # Add new entry
    tracked_ips.append({
        'ip': ip,
        'banned_at': datetime.utcnow().isoformat() + 'Z',
        'reason': reason
    })
    
    # Keep only last 100
    tracked_ips = tracked_ips[-100:]
    
    cache.set('security:banned_ips_list', tracked_ips, 86400)  # 24 hours

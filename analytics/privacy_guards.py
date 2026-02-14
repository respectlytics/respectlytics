"""
Privacy Guards for Respectlytics Event Ingestion API

This module implements strict privacy protection to prevent tracking identifiers
and personally identifiable information (PII) from being stored in the system.

Design Principles:
1. STRICT ALLOWLIST - Only explicitly allowed fields are accepted
2. HELPFUL ERRORS - Developers get clear feedback to fix their integration
3. FAIL FAST - Reject invalid requests before any processing
4. MINIMAL OVERHEAD - O(1) lookups and precompiled regex for <1ms impact
5. SESSION-BASED ANALYTICS - No persistent user IDs, no cross-session tracking
6. MINIMAL DATA STORAGE - Only 5 fields stored (event_name, timestamp, platform, country, session_id)

PRIVACY MODEL (Return of Avoidance - ROA):
- The best way to handle sensitive data is to never collect it
- Session IDs are ephemeral (in-memory only, 2-hour rotation in SDKs)
- No persistent user identifiers accepted or stored
- No cross-session tracking possible
- Only 5 essential fields stored; 6 deprecated fields silently ignored
- Transparent about what is collected, defensible by design, clear about why

This ensures Respectlytics remains a truly privacy-first analytics platform
that cannot be misused for user tracking.
"""

import re
import hashlib
import logging
from datetime import date
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)


class PrivacyValidationError(Exception):
    """
    Exception raised when a privacy violation is detected.
    
    Attributes:
        code: Machine-readable error code
        reason: Human-readable explanation for developers
        field: The field that caused the violation (if applicable)
    """
    def __init__(self, code: str, reason: str, field: Optional[str] = None):
        self.code = code
        self.reason = reason
        self.field = field
        super().__init__(reason)
    
    def to_response_dict(self) -> Dict[str, str]:
        """Return error details for API response."""
        return {
            "detail": "Invalid request",
            "code": self.code,
            "reason": self.reason
        }


# =============================================================================
# STRICT ALLOWLIST - Only these fields are accepted
# =============================================================================

ALLOWED_FIELDS = frozenset({
    # Authentication (handled separately, but may appear in request body)
    'app_key',

    # Required event data
    'event_name',

    # Optional timing
    'timestamp',

    # Optional technical context (non-identifying)
    'platform',       # ios, android, web, other
    'app_version',    # e.g., "2.1.0" - DEPRECATED: accepted but not stored
    'os_version',     # e.g., "iOS 17.1", "Android 14" - DEPRECATED: accepted but not stored
    'device_type',    # e.g., "iPhone 15", "Pixel 8" - DEPRECATED: accepted but not stored
    'locale',         # e.g., "en-US", "de-DE" - DEPRECATED: accepted but not stored

    # Optional geographic context (coarse, non-precise)
    'country',        # 2-letter ISO code
    'region',         # State/province name - DEPRECATED: accepted but not stored

    # Optional behavioral context
    'screen',         # Current screen/page name - DEPRECATED: accepted but not stored
    'session_id',     # Ephemeral session ID - see validate_session_id()
})


# =============================================================================
# STORED FIELDS - Fields that are actually persisted to the database
# =============================================================================
# These are the minimal fields needed for privacy-compliant analytics.
# Deprecated fields (app_version, os_version, device_type, locale, region, screen)
# are still accepted by the API for backwards compatibility with existing SDKs,
# but are silently ignored and not stored.

STORED_FIELDS = frozenset({
    'app_key',        # Authentication - used to link to App, not stored in Event row
    'event_name',     # Required - the action being tracked
    'timestamp',      # When the event occurred
    'platform',       # ios, android, web, other
    'country',        # 2-letter ISO code (derived from IP, IP discarded)
    'session_id',     # Ephemeral session ID (hashed server-side with daily rotation)
})

# Fields that are accepted but not stored (for backwards compatibility)
DEPRECATED_FIELDS = ALLOWED_FIELDS - STORED_FIELDS


# =============================================================================
# SESSION ID VALIDATION
# =============================================================================

# Session ID constraints
SESSION_ID_MIN_LENGTH = 16   # Minimum for adequate entropy
SESSION_ID_MAX_LENGTH = 128  # Reasonable upper limit

# Patterns that indicate misuse of session_id as a tracking identifier
SESSION_ID_FORBIDDEN_PATTERNS = [
    # IDFA/GAID format (uppercase hex UUID) - most common tracking ID format
    re.compile(r'^[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}$'),
    
    # Standard UUID format (any case) - could be device/vendor ID
    re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'),
    
    # Sequential/predictable patterns that could be user IDs
    re.compile(r'^(session|user|device|id|uid|sid)[-_]?\d+$', re.IGNORECASE),
    
    # Pure numeric (could be user ID, timestamp-based, or sequential)
    re.compile(r'^\d+$'),
    
    # Very short alphanumeric that's likely a user ID
    re.compile(r'^[a-zA-Z]{1,3}\d+$'),  # e.g., "u123", "usr456"
]


def validate_session_id(session_id: str) -> None:
    """
    Validate that session_id meets privacy requirements.
    
    Session IDs must:
    - Be between 16-128 characters (adequate entropy)
    - Not match known tracking identifier patterns
    - Not be predictable/sequential
    
    Args:
        session_id: The session ID to validate
        
    Raises:
        PrivacyValidationError: If session_id fails validation
    """
    if not session_id:
        return  # None/empty is allowed (field is optional)
    
    # Check length
    if len(session_id) < SESSION_ID_MIN_LENGTH:
        raise PrivacyValidationError(
            code="INVALID_SESSION_ID",
            reason=f"session_id must be at least {SESSION_ID_MIN_LENGTH} characters. "
                   f"Use a random string (e.g., UUID v4 lowercase, base64, or hex) "
                   f"generated fresh for each app session.",
            field="session_id"
        )
    
    if len(session_id) > SESSION_ID_MAX_LENGTH:
        raise PrivacyValidationError(
            code="INVALID_SESSION_ID",
            reason=f"session_id must not exceed {SESSION_ID_MAX_LENGTH} characters.",
            field="session_id"
        )
    
    # Check against forbidden patterns
    for pattern in SESSION_ID_FORBIDDEN_PATTERNS:
        if pattern.match(session_id):
            raise PrivacyValidationError(
                code="INVALID_SESSION_ID",
                reason="session_id appears to be a device identifier or predictable pattern. "
                       "Use a random string generated fresh for each app session. "
                       "Example: lowercase UUID v4, random hex, or base64 string.",
                field="session_id"
            )


# =============================================================================
# SESSION ID ANONYMIZATION (Daily Rotation)
# =============================================================================

def anonymize_session_id(session_id: str, app_id: str, rotation_date: date = None) -> str:
    """
    Anonymize a session ID using daily rotation.
    
    This function transforms client-provided session IDs into privacy-safe
    hashes that automatically rotate daily. This prevents cross-session tracking
    while preserving intra-day session analysis capabilities.
    
    Privacy Benefits:
    - Client session IDs are NEVER stored in the database
    - Same client session_id produces different hashes on different days
    - Cannot reverse-engineer original session_id from stored hash
    - Defensible by design - minimal data surface
    
    How it works:
    1. Combines session_id with app_id and current date
    2. Produces SHA256 hash truncated to 32 characters
    3. Hash changes automatically at midnight UTC
    
    Args:
        session_id: The client-provided session ID (already validated)
        app_id: The app's UUID string (for namespace isolation)
        rotation_date: Override date for testing (defaults to today UTC)
        
    Returns:
        32-character hex string (anonymized session ID)
        
    Example:
        >>> anonymize_session_id("abc123xyz789def456", "app-uuid-here")
        'f47ac10b58cc4372a5670e02b2c3d479'  # Changes daily
    """
    if not session_id:
        return None
    
    # Use provided date or today's date in UTC
    if rotation_date is None:
        rotation_date = date.today()
    
    # Create daily salt: app_id isolates apps, date provides rotation
    # Format: "app_id:YYYY-MM-DD"
    daily_salt = f"{app_id}:{rotation_date.isoformat()}"
    
    # Combine session_id with daily salt
    combined = f"{session_id}:{daily_salt}"
    
    # SHA256 hash, truncated to 32 chars (128 bits - sufficient for uniqueness)
    hashed = hashlib.sha256(combined.encode('utf-8')).hexdigest()[:32]
    
    return hashed


# =============================================================================
# VALUE VALIDATION (for allowed fields)
# =============================================================================

# Patterns that should never appear in ANY field value
FORBIDDEN_VALUE_PATTERNS = [
    # Email addresses
    (re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'), 
     "email address"),
    
    # Phone numbers (E.164 format)
    (re.compile(r'^\+[1-9]\d{6,14}$'), 
     "phone number"),
    
    # US phone format
    (re.compile(r'^\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}$'), 
     "phone number"),
    
    # IMEI numbers (15 digits, sometimes with check digit)
    (re.compile(r'^\d{15,17}$'), 
     "IMEI or similar device identifier"),
    
    # MAC addresses
    (re.compile(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$'), 
     "MAC address"),
    
    # IPv4 addresses (should not be in event data - we extract from request)
    (re.compile(r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'), 
     "IP address"),
    
    # US SSN format
    (re.compile(r'^\d{3}-\d{2}-\d{4}$'), 
     "social security number or similar identifier"),
]

# Fields where we should check for PII patterns in values
# (not all fields - e.g., event_name could legitimately be "user_signup")
FIELDS_TO_CHECK_VALUES = frozenset({
    'device_type',
    'os_version', 
    'screen',
    'region',
})


def validate_field_value(field_name: str, value: Any) -> None:
    """
    Validate that a field value doesn't contain PII patterns.
    
    Only checks specific fields where PII might accidentally appear.
    
    Args:
        field_name: Name of the field
        value: Value to validate
        
    Raises:
        PrivacyValidationError: If value contains forbidden pattern
    """
    if field_name not in FIELDS_TO_CHECK_VALUES:
        return
    
    if not isinstance(value, str) or not value:
        return
    
    for pattern, description in FORBIDDEN_VALUE_PATTERNS:
        if pattern.match(value):
            raise PrivacyValidationError(
                code="FORBIDDEN_VALUE",
                reason=f"Field '{field_name}' appears to contain a {description}. "
                       f"Respectlytics does not accept personally identifiable information.",
                field=field_name
            )


# =============================================================================
# MAIN VALIDATION FUNCTION
# =============================================================================

def validate_request_privacy(data: Dict[str, Any], app_key_for_logging: str = None) -> None:
    """
    Validate that request data complies with privacy requirements.
    
    This is the main entry point for privacy validation. It performs:
    1. Strict allowlist check - rejects any unknown fields
    2. Session ID validation - ensures it's not a tracking identifier
    3. Value pattern check - detects PII in field values
    
    Args:
        data: The request data dictionary
        app_key_for_logging: Optional app key hash for logging violations
        
    Raises:
        PrivacyValidationError: If any privacy violation is detected
    """
    if not isinstance(data, dict):
        raise PrivacyValidationError(
            code="INVALID_REQUEST",
            reason="Request body must be a JSON object."
        )
    
    # Step 1: Check for unknown fields (strict allowlist)
    unknown_fields = set(data.keys()) - ALLOWED_FIELDS
    if unknown_fields:
        # Log the violation for pattern detection
        field_list = ', '.join(sorted(unknown_fields))
        logger.warning(
            f"Privacy violation: Unknown fields rejected: [{field_list}]"
            + (f" (app: {app_key_for_logging[:8]}...)" if app_key_for_logging else "")
        )
        
        # Provide helpful error message
        if len(unknown_fields) == 1:
            field = next(iter(unknown_fields))
            raise PrivacyValidationError(
                code="FORBIDDEN_FIELD",
                reason=f"Field '{field}' is not allowed. "
                       f"Respectlytics only accepts these fields: {', '.join(sorted(ALLOWED_FIELDS))}. "
                       f"This restriction protects user privacy.",
                field=field
            )
        else:
            raise PrivacyValidationError(
                code="FORBIDDEN_FIELDS",
                reason=f"Fields [{field_list}] are not allowed. "
                       f"Respectlytics only accepts these fields: {', '.join(sorted(ALLOWED_FIELDS))}. "
                       f"This restriction protects user privacy."
            )
    
    # Step 2: Validate session_id if present
    if 'session_id' in data and data['session_id']:
        validate_session_id(data['session_id'])
    
    # Step 3: Check field values for PII patterns
    for field_name, value in data.items():
        validate_field_value(field_name, value)


# =============================================================================
# DOCUMENTATION HELPERS
# =============================================================================

def get_allowed_fields_documentation() -> str:
    """Return formatted documentation of allowed fields for API docs."""
    return """
## Accepted Fields

Respectlytics uses a strict allowlist for privacy protection. Only these fields are accepted:

| Field | Required | Description |
|-------|----------|-------------|
| `event_name` | ✅ Yes | Name of the event (e.g., "app_open", "purchase") |
| `timestamp` | No | ISO 8601 timestamp (defaults to server time) |
| `platform` | No | Platform: "ios", "android", "web", "other" |
| `app_version` | No | Your app version (e.g., "2.1.0") |
| `os_version` | No | OS version (e.g., "iOS 17.1") |
| `device_type` | No | Device model (e.g., "iPhone 15") - NOT a unique identifier |
| `locale` | No | User locale (e.g., "en-US") |
| `country` | No | 2-letter country code (auto-detected from IP if omitted) |
| `region` | No | State/province name (auto-detected from IP if omitted) |
| `screen` | No | Current screen/page name |
| `session_id` | No | Random session identifier (see Session ID section) |

### Session ID Requirements

If you include `session_id`, it must:
- Be at least 16 characters long
- Be randomly generated for each app session
- NOT be a device identifier (IDFA, GAID, etc.)
- NOT be a predictable pattern (e.g., "session_1", "user_123")

**Good examples:** `a1b2c3d4e5f6g7h8i9j0`, `f47ac10b58cc4372a567`, `Xt7kL9mN2pQ4rS6u`

### Session-Based Analytics (Privacy by Design)

Respectlytics uses **session-based analytics** with minimal data collection:

1. **No persistent user IDs** - The SDK generates ephemeral session IDs in memory
2. **2-hour rotation** - Session IDs automatically rotate every 2 hours
3. **App restart = new session** - No cross-session tracking possible
4. **No device storage** - Nothing stored in Keychain/SharedPreferences

**What this means:**
- Single-session funnel analysis works perfectly
- Cross-session tracking is **impossible** by design
- Our system is transparent, defensible, and clear about data collection
- Only 5 fields stored: event_name, timestamp, platform, country, session_id

### Forbidden Data

The following are **never accepted** to protect user privacy:
- Device identifiers (IDFA, GAID, Android ID, IMEI, MAC address)
- User identifiers (user_id, email, phone number)
- Precise location (GPS coordinates, IP address)
- Personal information (name, address, SSN, etc.)
- Custom fields or metadata not in the allowlist above

Any request containing forbidden fields will be rejected with a `400 Bad Request` response.
"""

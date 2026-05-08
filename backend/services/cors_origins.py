"""
CORS origin management utilities.
Provides dynamic CORS validation and origin retrieval.
Supports wildcard patterns like *.domain.fr
"""

import logging
import fnmatch
from urllib.parse import urlparse

from models.cors import AllowedOrigin

logger = logging.getLogger(__name__)


def extract_domain_from_origin(origin: str) -> str:
    """Extract domain from origin URL (e.g., https://sub.domain.fr:8080 -> sub.domain.fr)."""
    try:
        parsed = urlparse(origin)
        # Get hostname without port
        return parsed.hostname or origin
    except Exception:
        return origin


def matches_pattern(domain: str, pattern: str) -> bool:
    """
    Check if domain matches pattern, supporting wildcards.
    
    Examples:
    - matches_pattern('sub.domain.fr', '*.domain.fr') -> True
    - matches_pattern('domain.fr', '*.domain.fr') -> False
    - matches_pattern('app.sub.domain.fr', '*.sub.domain.fr') -> True
    - matches_pattern('domain.fr', 'domain.fr') -> True (exact match)
    """
    return fnmatch.fnmatch(domain, pattern)


def is_origin_allowed(origin: str) -> bool:
    """Check if an origin is allowed and active.
    
    Supports both exact matches and wildcard patterns:
    - Exact: 'https://domain.fr'
    - Wildcard: '*.domain.fr' (matches any subdomain of domain.fr)
    """
    if not origin:
        return False
    
    domain = extract_domain_from_origin(origin)
    
    # Check allowed origins
    allowed_origins = AllowedOrigin.query.filter_by(active=True).all()
    
    for allowed in allowed_origins:
        pattern = allowed.origin
        
        # If pattern is a full URL, extract domain for comparison
        if pattern.startswith(('http://', 'https://', 'ws://', 'wss://')):
            pattern = extract_domain_from_origin(pattern)
        
        # Check if domain matches the pattern
        if matches_pattern(domain, pattern):
            return True
    
    return False


def get_all_origins():
    """Get list of all active allowed origins."""
    return [o.origin for o in AllowedOrigin.query.filter_by(active=True).all()]


def dynamic_origin(origin):
    """Callback for Flask-CORS to allow/disallow origins dynamically."""
    return origin if is_origin_allowed(origin) else False

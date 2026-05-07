"""
CORS origin management utilities.
Provides dynamic CORS validation and origin retrieval.
"""

import logging
from models.cors import AllowedOrigin

logger = logging.getLogger(__name__)


def is_origin_allowed(origin: str) -> bool:
    """Check if an origin is allowed and active."""
    if not origin:
        return False
    return AllowedOrigin.query.filter_by(origin=origin, active=True).first() is not None


def get_all_origins():
    """Get list of all active allowed origins."""
    return [o.origin for o in AllowedOrigin.query.filter_by(active=True).all()]


def dynamic_origin(origin):
    """Callback for Flask-CORS to allow/disallow origins dynamically."""
    return origin if is_origin_allowed(origin) else False

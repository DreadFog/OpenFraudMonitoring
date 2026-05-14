"""Custom filter package facade.

This package splits filter logic into focused modules while preserving the
original API consumed by schema registry, routes, and rules engine.
"""

from .registry import (
    register_custom_filter,
    get_custom_handler,
    get_custom_fields,
    get_custom_suggestions,
    get_custom_aggregate,
)
from . import ip_filters, behavior_filters


# Register built-ins at import time.
ip_filters.register_filters()
behavior_filters.register_filters()


__all__ = [
    "register_custom_filter",
    "get_custom_handler",
    "get_custom_fields",
    "get_custom_suggestions",
    "get_custom_aggregate",
]

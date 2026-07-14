"""
Settings service — defaults and helpers for user-scoped and global settings.

User settings live in `users.settings` (JSONB).  Global settings live in the
`app_settings` table.  This module centralizes the canonical defaults and the
merge/validation logic so routes stay thin.
"""

from __future__ import annotations

import copy

from services.database import db
from models.app_setting import AppSetting


# ─────────────────────────────────────────────────────────────────────────────
# Global settings
# ─────────────────────────────────────────────────────────────────────────────

# Default warning threshold: expansions that would add this many (or more)
# nodes prompt a confirmation in the graph UI.
GRAPH_EXPAND_WARN_THRESHOLD_KEY = "graph.expand_warn_threshold"

GLOBAL_DEFAULTS = {
    GRAPH_EXPAND_WARN_THRESHOLD_KEY: 1000,
}


def get_global_setting(key: str):
    """Return the stored value for `key`, or its default."""
    row = AppSetting.query.get(key)
    if row is not None and row.value is not None and "value" in row.value:
        return row.value["value"]
    return GLOBAL_DEFAULTS.get(key)


def set_global_setting(key: str, value) -> None:
    """Upsert a global setting value."""
    row = AppSetting.query.get(key)
    if row is None:
        row = AppSetting(key=key, value={"value": value})
        db.session.add(row)
    else:
        row.value = {"value": value}
    db.session.commit()


def get_global_settings() -> dict:
    """Return all known global settings merged over defaults."""
    result = dict(GLOBAL_DEFAULTS)
    for row in AppSetting.query.all():
        if isinstance(row.value, dict) and "value" in row.value:
            result[row.key] = row.value["value"]
    return result


def get_graph_expand_threshold() -> int:
    try:
        return int(get_global_setting(GRAPH_EXPAND_WARN_THRESHOLD_KEY))
    except (TypeError, ValueError):
        return GLOBAL_DEFAULTS[GRAPH_EXPAND_WARN_THRESHOLD_KEY]


# ─────────────────────────────────────────────────────────────────────────────
# User settings
# ─────────────────────────────────────────────────────────────────────────────

# Canonical default graph visualization settings.  Colors are hex strings.
USER_SETTINGS_DEFAULTS = {
    "graph": {
        "colors": {
            "session": "#3b82f6",
            "property": "#a78bfa",
            "flag": "#f59e0b",
            "stix": {
                "ipv4-addr": "#10b981",
                "ipv6-addr": "#14b8a6",
                "user-agent": "#f59e0b",
                "autonomous-system": "#6366f1",
                "location": "#ec4899",
                "indicator": "#ef4444",
                "malware": "#dc2626",
                "campaign": "#8b5cf6",
                "intrusion-set": "#f97316",
            },
        },
        "riskRing": {
            "enabled": True,
            "color": "#ef4444",
        },
        "autoLink": True,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` into a copy of `base`."""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_user_settings(user) -> dict:
    """Return the user's settings merged over the canonical defaults."""
    return _deep_merge(USER_SETTINGS_DEFAULTS, user.settings or {})


def update_user_settings(user, patch: dict) -> dict:
    """Merge `patch` into the user's stored settings and persist."""
    merged = _deep_merge(user.settings or {}, patch or {})
    user.settings = merged
    db.session.commit()
    return get_user_settings(user)

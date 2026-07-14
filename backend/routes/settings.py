"""
Settings routes.

  GET  /api/settings/me         — current user's settings (merged with defaults)
  PUT  /api/settings/me         — merge a patch into the current user's settings
  GET  /api/settings/global     — global settings (any authenticated user)
  PUT  /api/settings/global     — update a global setting (admin only)
"""

import logging

from flask import Blueprint, request, jsonify, g

from services.auth import require_auth, require_role
from services.settings import (
    get_user_settings,
    update_user_settings,
    get_global_settings,
    set_global_setting,
    GRAPH_EXPAND_WARN_THRESHOLD_KEY,
)

logger = logging.getLogger(__name__)

settings_bp = Blueprint("settings", __name__, url_prefix="/api/settings")


@settings_bp.route("/me", methods=["GET"])
@require_auth
def get_my_settings():
    return jsonify(get_user_settings(g.current_user)), 200


@settings_bp.route("/me", methods=["PUT"])
@require_auth
def update_my_settings():
    patch = request.get_json(silent=True)
    if not isinstance(patch, dict):
        return jsonify({"error": "body must be a JSON object"}), 400
    return jsonify(update_user_settings(g.current_user, patch)), 200


@settings_bp.route("/global", methods=["GET"])
@require_auth
def get_globals():
    return jsonify(get_global_settings()), 200


# Keys that admins are allowed to set, with their validators.
_ALLOWED_GLOBAL_KEYS = {
    GRAPH_EXPAND_WARN_THRESHOLD_KEY: lambda v: int(v) if int(v) >= 1 else None,
}


@settings_bp.route("/global", methods=["PUT"])
@require_auth
@require_role("admin")
def update_globals():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "body must be a JSON object"}), 400

    updated = {}
    for key, raw in body.items():
        validator = _ALLOWED_GLOBAL_KEYS.get(key)
        if validator is None:
            return jsonify({"error": f"unknown or read-only setting: {key}"}), 400
        try:
            value = validator(raw)
        except (TypeError, ValueError):
            value = None
        if value is None:
            return jsonify({"error": f"invalid value for {key}"}), 400
        set_global_setting(key, value)
        updated[key] = value

    return jsonify({"ok": True, "updated": updated, "settings": get_global_settings()}), 200

"""
CORS origin management API routes (admin only).
"""

import logging
from flask import Blueprint, request, jsonify
from models.cors import AllowedOrigin
from services.database import db
from services.auth import require_auth, require_role

logger = logging.getLogger(__name__)

cors_bp = Blueprint("cors", __name__, url_prefix="/api/admin/cors")


@cors_bp.route("/origins", methods=["GET"])
@require_auth
@require_role("admin")
def list_origins():
    """List all CORS allowed origins."""
    origins = AllowedOrigin.query.order_by(AllowedOrigin.created_at.desc()).all()
    return jsonify([o.to_dict() for o in origins]), 200


@cors_bp.route("/origins", methods=["POST"])
@require_auth
@require_role("admin")
def add_origin():
    """Add a new CORS allowed origin."""
    origin = request.json.get("origin", "").strip()
    if not origin:
        return jsonify({"error": "origin required"}), 400
    
    # Validate origin format (basic check)
    if not (origin.startswith("http://") or origin.startswith("https://")):
        return jsonify({"error": "origin must start with http:// or https://"}), 400
    
    # Check for duplicates
    if AllowedOrigin.query.filter_by(origin=origin).first():
        return jsonify({"error": "origin already exists"}), 409
    
    try:
        new_origin = AllowedOrigin(origin=origin, active=True)
        db.session.add(new_origin)
        db.session.commit()
        logger.info("Admin added CORS origin: %s", origin)
        return jsonify(new_origin.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        logger.error("Failed to add CORS origin: %s", e)
        return jsonify({"error": "failed to add origin"}), 500


@cors_bp.route("/origins/<int:origin_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def remove_origin(origin_id):
    """Remove a CORS allowed origin."""
    origin_obj = AllowedOrigin.query.get_or_404(origin_id)
    try:
        db.session.delete(origin_obj)
        db.session.commit()
        logger.info("Admin removed CORS origin: %s", origin_obj.origin)
        return jsonify({"message": "origin removed"}), 200
    except Exception as e:
        db.session.rollback()
        logger.error("Failed to remove CORS origin: %s", e)
        return jsonify({"error": "failed to remove origin"}), 500


@cors_bp.route("/origins/<int:origin_id>/toggle", methods=["PATCH"])
@require_auth
@require_role("admin")
def toggle_origin(origin_id):
    """Toggle active status of a CORS origin."""
    origin_obj = AllowedOrigin.query.get_or_404(origin_id)
    try:
        origin_obj.active = not origin_obj.active
        db.session.commit()
        logger.info("Admin toggled CORS origin %s to active=%s", origin_obj.origin, origin_obj.active)
        return jsonify(origin_obj.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        logger.error("Failed to toggle CORS origin: %s", e)
        return jsonify({"error": "failed to toggle origin"}), 500

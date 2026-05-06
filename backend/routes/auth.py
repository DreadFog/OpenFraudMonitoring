"""
Auth routes — login, profile, password change, API token management, user CRUD.
"""

import logging
from datetime import datetime

from flask import Blueprint, request, jsonify, g

from services.database import db
from services.auth import (
    hash_password,
    check_password,
    create_jwt,
    generate_api_token,
    hash_api_token,
    require_auth,
    require_role,
)
from models.user import User, ApiToken

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# ─────────────────────────────────────────────────────────────────────────────
# Public
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["POST"])
def login():
    """Authenticate with username + password, return a short-lived JWT."""
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    user = User.query.filter_by(username=username).first()
    if user is None or not user.is_active:
        return jsonify({"error": "invalid credentials"}), 401
    if not user.password_hash:
        return jsonify({"error": "password login not available for this account"}), 401
    if not check_password(password, user.password_hash):
        return jsonify({"error": "invalid credentials"}), 401

    token = create_jwt(user.id, user.role)
    return jsonify({"token": token, "user": user.to_dict()}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Authenticated — any role
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/me", methods=["GET"])
@require_auth
def me():
    """Return the current user's profile and their API tokens (metadata only)."""
    tokens = ApiToken.query.filter_by(user_id=g.current_user.id).order_by(ApiToken.created_at.desc()).all()
    return jsonify({
        "user": g.current_user.to_dict(),
        "tokens": [t.to_dict() for t in tokens],
    }), 200


@auth_bp.route("/password", methods=["PUT"])
@require_auth
def change_password():
    """Change the current user's password."""
    body = request.get_json(silent=True) or {}
    current_pw = body.get("current_password") or ""
    new_pw = body.get("new_password") or ""

    if not current_pw or not new_pw:
        return jsonify({"error": "current_password and new_password are required"}), 400
    if len(new_pw) < 8:
        return jsonify({"error": "new_password must be at least 8 characters"}), 400

    if not g.current_user.password_hash or not check_password(current_pw, g.current_user.password_hash):
        return jsonify({"error": "current password is incorrect"}), 401

    g.current_user.password_hash = hash_password(new_pw)
    db.session.commit()
    return jsonify({"ok": True}), 200


# ─────────────────────────────────────────────────────────────────────────────
# API token management (self-service)
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/tokens", methods=["GET"])
@require_auth
def list_tokens():
    """List the current user's API tokens (metadata only, never the raw token)."""
    tokens = ApiToken.query.filter_by(user_id=g.current_user.id).order_by(ApiToken.created_at.desc()).all()
    return jsonify([t.to_dict() for t in tokens]), 200


@auth_bp.route("/tokens", methods=["POST"])
@require_auth
def create_token():
    """Create a new API token for the current user.  The raw token is returned only once."""
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "default").strip()[:128]
    expires_at_str = body.get("expires_at")

    expires_at = None
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return jsonify({"error": "invalid expires_at format"}), 400

    raw_token = generate_api_token()
    token_obj = ApiToken(
        user_id=g.current_user.id,
        token_hash=hash_api_token(raw_token),
        token_prefix=raw_token[:12],
        name=name,
        expires_at=expires_at,
    )
    db.session.add(token_obj)
    db.session.commit()

    return jsonify({
        "token": raw_token,
        "id": token_obj.id,
        "name": token_obj.name,
        "token_prefix": token_obj.token_prefix,
        "expires_at": token_obj.expires_at.isoformat() if token_obj.expires_at else None,
    }), 201


@auth_bp.route("/tokens/<int:token_id>", methods=["DELETE"])
@require_auth
def revoke_token(token_id):
    """Revoke one of the current user's API tokens."""
    token_obj = ApiToken.query.filter_by(id=token_id, user_id=g.current_user.id).first()
    if token_obj is None:
        return jsonify({"error": "token not found"}), 404
    db.session.delete(token_obj)
    db.session.commit()
    return jsonify({"ok": True}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Admin — user management
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/users", methods=["GET"])
@require_auth
@require_role("admin")
def list_users():
    """List all users."""
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([u.to_dict() for u in users]), 200


@auth_bp.route("/users", methods=["POST"])
@require_auth
@require_role("admin")
def create_user():
    """Create a new user.  Password is optional for connector-role users."""
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    role = (body.get("role") or "user").strip().lower()

    if not username:
        return jsonify({"error": "username is required"}), 400
    if role not in ("user", "admin", "connector"):
        return jsonify({"error": "role must be user, admin, or connector"}), 400
    if role != "connector" and not password:
        return jsonify({"error": "password is required for user/admin roles"}), 400
    if password and len(password) < 8:
        return jsonify({"error": "password must be at least 8 characters"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "username already exists"}), 409

    user = User(
        username=username,
        password_hash=hash_password(password) if password else None,
        role=role,
    )
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


@auth_bp.route("/users/<int:user_id>", methods=["PUT"])
@require_auth
@require_role("admin")
def update_user(user_id):
    """Update a user's role or active status."""
    user = User.query.get(user_id)
    if user is None:
        return jsonify({"error": "user not found"}), 404

    body = request.get_json(silent=True) or {}
    if "role" in body:
        role = body["role"].strip().lower()
        if role not in ("user", "admin", "connector"):
            return jsonify({"error": "role must be user, admin, or connector"}), 400
        user.role = role
    if "is_active" in body:
        user.is_active = bool(body["is_active"])
    if "password" in body and body["password"]:
        if len(body["password"]) < 8:
            return jsonify({"error": "password must be at least 8 characters"}), 400
        user.password_hash = hash_password(body["password"])

    db.session.commit()
    return jsonify(user.to_dict()), 200


@auth_bp.route("/users/<int:user_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def delete_user(user_id):
    """Delete a user and revoke all their tokens."""
    if user_id == g.current_user.id:
        return jsonify({"error": "cannot delete yourself"}), 400

    user = User.query.get(user_id)
    if user is None:
        return jsonify({"error": "user not found"}), 404

    db.session.delete(user)
    db.session.commit()
    return jsonify({"ok": True}), 200


@auth_bp.route("/users/<int:user_id>/tokens", methods=["POST"])
@require_auth
@require_role("admin")
def create_user_token(user_id):
    """Admin: create an API token for any user (used for connector bootstrapping)."""
    user = User.query.get(user_id)
    if user is None:
        return jsonify({"error": "user not found"}), 404

    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "default").strip()[:128]

    raw_token = generate_api_token()
    token_obj = ApiToken(
        user_id=user.id,
        token_hash=hash_api_token(raw_token),
        token_prefix=raw_token[:12],
        name=name,
    )
    db.session.add(token_obj)
    db.session.commit()

    return jsonify({
        "token": raw_token,
        "id": token_obj.id,
        "name": token_obj.name,
        "token_prefix": token_obj.token_prefix,
        "user": user.to_dict(),
    }), 201

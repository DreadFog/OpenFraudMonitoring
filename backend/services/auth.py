"""
Authentication utilities — password hashing, JWT, API tokens, decorators.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional

import jwt
from flask import current_app, g, jsonify, request
from flask_bcrypt import Bcrypt

logger = logging.getLogger(__name__)

bcrypt = Bcrypt()

# ── Password helpers ──


def hash_password(password: str) -> str:
    return bcrypt.generate_password_hash(password).decode("utf-8")


def check_password(password: str, password_hash: str) -> bool:
    return bcrypt.check_password_hash(password_hash, password)


# ── API token helpers ──


def generate_api_token() -> str:
    """Generate a raw API token in the format ``ofm_<32 hex chars>``."""
    return f"ofm_{secrets.token_hex(16)}"


def hash_api_token(token: str) -> str:
    """SHA-256 hash of a raw API token for storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── JWT helpers ──


def create_jwt(user_id: int, role: str, expires_hours: Optional[int] = None) -> str:
    secret = current_app.config["JWT_SECRET"]
    hours = expires_hours or int(current_app.config.get("JWT_EXPIRY_HOURS", 24))
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=hours),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_jwt(token: str) -> Optional[dict]:
    secret = current_app.config["JWT_SECRET"]
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ── Decorators ──


def require_auth(fn):
    """Decorator: validates Bearer token (JWT or API token), sets ``g.current_user``."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        from models.user import User, ApiToken

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "unauthorized"}), 401

        token = auth_header[len("Bearer "):].strip()
        if not token:
            return jsonify({"error": "unauthorized"}), 401

        user = None

        # Try API token lookup first (covers both ofm_ tokens and bootstrap tokens)
        token_hash = hash_api_token(token)
        api_token = ApiToken.query.filter_by(token_hash=token_hash, is_active=True).first()
        if api_token is not None:
            # Check expiration
            if api_token.expires_at and api_token.expires_at < datetime.utcnow():
                return jsonify({"error": "token expired"}), 401
            user = User.query.get(api_token.user_id)
            # Update last_used_at
            api_token.last_used_at = datetime.utcnow()
            from services.database import db
            db.session.commit()
        else:
            # JWT path
            payload = decode_jwt(token)
            if payload is None:
                return jsonify({"error": "unauthorized"}), 401
            user = User.query.get(payload["sub"])

        if user is None or not user.is_active:
            return jsonify({"error": "unauthorized"}), 401

        g.current_user = user
        return fn(*args, **kwargs)

    return wrapper


def require_role(*roles):
    """Decorator: checks ``g.current_user.role`` is in the allowed set.
    Must be applied **after** ``@require_auth``."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not hasattr(g, "current_user") or g.current_user.role not in roles:
                return jsonify({"error": "forbidden"}), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator

"""
Seed the database with a default admin user and bootstrap API token.

Safe to run multiple times — existing users/tokens are skipped.
"""

import logging

from services.database import db
from services.auth import hash_password, generate_api_token, hash_api_token
from models.user import User, ApiToken
from config import Config

logger = logging.getLogger(__name__)


def seed_default_admin():
    """Create the default admin user and bootstrap API token if they don't exist."""
    username = Config.OFM_ADMIN_USERNAME
    password = Config.OFM_ADMIN_PASSWORD
    admin_token_raw = Config.OFM_ADMIN_TOKEN

    admin = User.query.filter_by(username=username).first()
    if admin is None:
        admin = User(
            username=username,
            password_hash=hash_password(password),
            role="admin",
        )
        db.session.add(admin)
        db.session.flush()
        logger.info("Created default admin user: %s", username)

        if username == "admin" and password == "admin":
            logger.warning(
                "Default admin credentials (admin/admin) are in use. "
                "Set OFM_ADMIN_USERNAME and OFM_ADMIN_PASSWORD environment variables."
            )

    # Ensure bootstrap API token exists for the admin user
    if admin_token_raw:
        token_hash = hash_api_token(admin_token_raw)
        existing_token = ApiToken.query.filter_by(token_hash=token_hash).first()
        if existing_token is None:
            db.session.add(ApiToken(
                user_id=admin.id,
                token_hash=token_hash,
                token_prefix=admin_token_raw[:12] if len(admin_token_raw) >= 12 else admin_token_raw,
                name="bootstrap",
            ))
            logger.info("Created bootstrap API token for admin user")

        if admin_token_raw == "dev-admin-token":
            logger.warning(
                "Default bootstrap admin token is in use. "
                "Set OFM_ADMIN_TOKEN environment variable."
            )

    db.session.commit()

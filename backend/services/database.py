"""
Database configuration and session management
"""

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

db = SQLAlchemy()

_SCHEMA_INIT_LOCK_KEY = 88442211


def _create_all_safely():
    """Create DB schema with a cross-process lock to avoid startup races."""
    engine = db.engine
    if engine.dialect.name != "postgresql":
        db.create_all()
        return

    with engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _SCHEMA_INIT_LOCK_KEY})
        try:
            db.metadata.create_all(bind=conn)
            conn.commit()
        except IntegrityError as e:
            # Another process may have created a table concurrently.
            conn.rollback()
            if "pg_type_typname_nsp_index" not in str(e.orig):
                raise
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SCHEMA_INIT_LOCK_KEY})
            conn.commit()


# Idempotent column additions for tables that already exist in older
# deployments.  This repo has no migration tool, so `create_all` will not add
# new columns to existing tables — we apply the small set of additive changes
# here.  Each statement is safe to run repeatedly.
_COLUMN_UPGRADES = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS settings JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS device_id INTEGER REFERENCES devices(id)",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS is_mobile BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS device_type VARCHAR(16) NOT NULL DEFAULT 'unknown'",
]


def _apply_column_upgrades():
    """Apply additive column upgrades on PostgreSQL (no-op elsewhere)."""
    engine = db.engine
    if engine.dialect.name != "postgresql":
        return
    with engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _SCHEMA_INIT_LOCK_KEY})
        try:
            for stmt in _COLUMN_UPGRADES:
                conn.execute(text(stmt))
            conn.commit()
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SCHEMA_INIT_LOCK_KEY})
            conn.commit()


def init_db(app):
    """Initialize the database with the Flask app"""
    db.init_app(app)
    with app.app_context():
        _create_all_safely()
        _apply_column_upgrades()

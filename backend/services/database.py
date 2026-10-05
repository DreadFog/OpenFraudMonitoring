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
    "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS latency JSONB",
    "ALTER TABLE heartbeats ADD COLUMN IF NOT EXISTS latency JSONB",
    "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS visit_id VARCHAR(36)",
    "UPDATE sessions SET visit_id = gen_random_uuid()::text WHERE visit_id IS NULL",
    "ALTER TABLE sessions ALTER COLUMN visit_id SET NOT NULL",
    "ALTER TABLE sessions DROP CONSTRAINT IF EXISTS sessions_fsid_key",
    "DROP INDEX IF EXISTS ix_sessions_fsid",
    "CREATE INDEX IF NOT EXISTS ix_sessions_fsid ON sessions (fsid)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_sessions_visit_id ON sessions (visit_id)",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS cpu_count DOUBLE PRECISION DEFAULT 0",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS memory DOUBLE PRECISION DEFAULT 0",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS match_profile JSONB DEFAULT '{}'::jsonb",
    "ALTER TABLE device_cookies ADD COLUMN IF NOT EXISTS match_method VARCHAR(16) NOT NULL DEFAULT 'legacy'",
    "ALTER TABLE device_cookies ADD COLUMN IF NOT EXISTS match_confidence DOUBLE PRECISION",
    "ALTER TABLE device_cookies ADD COLUMN IF NOT EXISTS match_evidence JSONB DEFAULT '{}'::jsonb",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS settings JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS device_id INTEGER REFERENCES devices(id)",
    "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS authenticated BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS domains JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS is_mobile BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS device_type VARCHAR(16) NOT NULL DEFAULT 'unknown'",
    "ALTER TABLE heartbeats ADD COLUMN IF NOT EXISTS authenticated BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE fingerprints ADD COLUMN IF NOT EXISTS authenticated BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE beh_copy ADD COLUMN IF NOT EXISTS authenticated BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE beh_paste ADD COLUMN IF NOT EXISTS authenticated BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE beh_form_submit ADD COLUMN IF NOT EXISTS authenticated BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE beh_button_click ADD COLUMN IF NOT EXISTS authenticated BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE beh_auth_attempt ADD COLUMN IF NOT EXISTS authenticated BOOLEAN NOT NULL DEFAULT false",
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

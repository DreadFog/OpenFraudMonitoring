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


def init_db(app):
    """Initialize the database with the Flask app"""
    db.init_app(app)
    with app.app_context():
        _create_all_safely()

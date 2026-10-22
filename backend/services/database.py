"""
Database configuration and session management
"""

import os

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
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


def _run_schema_migrations(connection):
    """Apply ordered Alembic revisions using the existing database connection."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    migration_config = AlembicConfig(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    migration_config.set_main_option(
        "script_location",
        os.path.join(os.path.dirname(__file__), "..", "migrations"),
    )
    migration_config.attributes["connection"] = connection
    command.upgrade(migration_config, "head")


def _cleanup_legacy_stix_payloads(connection):
    """Remove the legacy revoked field from STIX types without platform revocation."""
    from models import StixIndicator

    inspector = inspect(connection)
    quote = connection.dialect.identifier_preparer.quote
    for table in db.metadata.sorted_tables:
        if not table.name.startswith("stix_") or table.name == StixIndicator.__tablename__:
            continue
        if inspector.has_table(table.name) and "raw" in table.c:
            connection.execute(text(
                f"UPDATE {quote(table.name)} SET raw = raw - 'revoked' WHERE raw ? 'revoked'"
            ))


def _apply_column_upgrades():
    """Run the repeatable legacy STIX payload cleanup used by maintenance tests."""
    if db.engine.dialect.name != "postgresql":
        return
    with db.engine.begin() as connection:
        _cleanup_legacy_stix_payloads(connection)


def init_db(app):
    """Initialize the database with the Flask app"""
    db.init_app(app)
    with app.app_context():
        import models  # noqa: F401 - ensure all model tables are registered

        engine = db.engine
        if engine.dialect.name == "postgresql":
            with engine.connect() as connection:
                connection.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _SCHEMA_INIT_LOCK_KEY})
                try:
                    _run_schema_migrations(connection)
                    db.metadata.create_all(bind=connection)
                    _cleanup_legacy_stix_payloads(connection)
                    connection.commit()
                finally:
                    connection.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SCHEMA_INIT_LOCK_KEY})
                    connection.commit()
            return
        _create_all_safely()

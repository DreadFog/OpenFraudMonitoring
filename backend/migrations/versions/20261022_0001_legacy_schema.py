"""Adopt the existing OFM schema into ordered Alembic migrations.

Revision ID: 20261022_0001
Revises:
"""

from alembic import op
from sqlalchemy import Boolean, inspect, text

from models import StixIndicator
from services.database import db


revision = "20261022_0001"
down_revision = None
branch_labels = None
depends_on = None


UPGRADES = (
    ("taxii_feeds", "ALTER TABLE taxii_feeds ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT false"),
    ("taxii_feeds", "ALTER TABLE taxii_feeds ADD COLUMN IF NOT EXISTS export_format VARCHAR(8) NOT NULL DEFAULT 'taxii'"),
    ("taxii_feeds", "ALTER TABLE taxii_feeds ADD COLUMN IF NOT EXISTS export_fields JSONB NOT NULL DEFAULT '[]'::jsonb"),
    ("taxii_feeds", "ALTER TABLE taxii_feeds ADD COLUMN IF NOT EXISTS include_headers BOOLEAN NOT NULL DEFAULT true"),
    ("taxii_feeds", "ALTER TABLE taxii_feeds ADD COLUMN IF NOT EXISTS csv_delimiter VARCHAR(1) NOT NULL DEFAULT ','"),
    ("taxii_feeds", "ALTER TABLE taxii_feeds ADD COLUMN IF NOT EXISTS auto_update BOOLEAN NOT NULL DEFAULT false"),
    ("taxii_feeds", "ALTER TABLE taxii_feeds ADD COLUMN IF NOT EXISTS update_interval_minutes INTEGER NOT NULL DEFAULT 60"),
    ("taxii_feeds", "ALTER TABLE taxii_feeds ADD COLUMN IF NOT EXISTS filter_logic VARCHAR(3) NOT NULL DEFAULT 'AND'"),
    ("taxii_feeds", "ALTER TABLE taxii_feeds ADD COLUMN IF NOT EXISTS matching_ids JSONB NOT NULL DEFAULT '[]'::jsonb"),
    ("taxii_feeds", "ALTER TABLE taxii_feeds ADD COLUMN IF NOT EXISTS csv_content TEXT"),
    ("taxii_feeds", "ALTER TABLE taxii_feeds ADD COLUMN IF NOT EXISTS last_generated_at TIMESTAMP"),
    ("stix_indicator", "ALTER TABLE stix_indicator ADD COLUMN IF NOT EXISTS name TEXT"),
    ("stix_indicator", "ALTER TABLE stix_indicator ADD COLUMN IF NOT EXISTS description TEXT"),
    ("stix_indicator", "UPDATE stix_indicator SET name = raw->>'name', description = raw->>'description' "
     "WHERE name IS DISTINCT FROM raw->>'name' OR description IS DISTINCT FROM raw->>'description'"),
    ("stix_indicator", "ALTER TABLE stix_indicator ADD COLUMN IF NOT EXISTS revoked BOOLEAN NOT NULL DEFAULT false"),
    ("stix_indicator", "UPDATE stix_indicator SET revoked = true WHERE raw->>'revoked' = 'true' AND NOT revoked"),
    ("sessions", "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS latency JSONB"),
    ("heartbeats", "ALTER TABLE heartbeats ADD COLUMN IF NOT EXISTS latency JSONB"),
    ("sessions", "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS visit_id VARCHAR(36)"),
    ("sessions", "UPDATE sessions SET visit_id = gen_random_uuid()::text WHERE visit_id IS NULL"),
    ("sessions", "ALTER TABLE sessions ALTER COLUMN visit_id SET NOT NULL"),
    ("sessions", "ALTER TABLE sessions DROP CONSTRAINT IF EXISTS sessions_fsid_key"),
    ("sessions", "DROP INDEX IF EXISTS ix_sessions_fsid"),
    ("sessions", "CREATE INDEX IF NOT EXISTS ix_sessions_fsid ON sessions (fsid)"),
    ("sessions", "CREATE UNIQUE INDEX IF NOT EXISTS ix_sessions_visit_id ON sessions (visit_id)"),
    ("devices", "ALTER TABLE devices ADD COLUMN IF NOT EXISTS cpu_count DOUBLE PRECISION DEFAULT 0"),
    ("devices", "ALTER TABLE devices ADD COLUMN IF NOT EXISTS memory DOUBLE PRECISION DEFAULT 0"),
    ("devices", "ALTER TABLE devices ADD COLUMN IF NOT EXISTS match_profile JSONB DEFAULT '{}'::jsonb"),
    ("device_cookies", "ALTER TABLE device_cookies ADD COLUMN IF NOT EXISTS match_method VARCHAR(16) NOT NULL DEFAULT 'legacy'"),
    ("device_cookies", "ALTER TABLE device_cookies ADD COLUMN IF NOT EXISTS match_confidence DOUBLE PRECISION"),
    ("device_cookies", "ALTER TABLE device_cookies ADD COLUMN IF NOT EXISTS match_evidence JSONB DEFAULT '{}'::jsonb"),
    ("users", "ALTER TABLE users ADD COLUMN IF NOT EXISTS settings JSONB NOT NULL DEFAULT '{}'::jsonb"),
    ("sessions", "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS device_id INTEGER REFERENCES devices(id)"),
    ("sessions", "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS authenticated BOOLEAN NOT NULL DEFAULT false"),
    ("sessions", "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS domains JSONB NOT NULL DEFAULT '[]'::jsonb"),
    ("devices", "ALTER TABLE devices ADD COLUMN IF NOT EXISTS is_mobile BOOLEAN NOT NULL DEFAULT false"),
    ("devices", "ALTER TABLE devices ADD COLUMN IF NOT EXISTS device_type VARCHAR(16) NOT NULL DEFAULT 'unknown'"),
    ("heartbeats", "ALTER TABLE heartbeats ADD COLUMN IF NOT EXISTS authenticated BOOLEAN NOT NULL DEFAULT false"),
    ("fingerprints", "ALTER TABLE fingerprints ADD COLUMN IF NOT EXISTS authenticated BOOLEAN NOT NULL DEFAULT false"),
    ("beh_copy", "ALTER TABLE beh_copy ADD COLUMN IF NOT EXISTS authenticated BOOLEAN NOT NULL DEFAULT false"),
    ("beh_paste", "ALTER TABLE beh_paste ADD COLUMN IF NOT EXISTS authenticated BOOLEAN NOT NULL DEFAULT false"),
    ("beh_form_submit", "ALTER TABLE beh_form_submit ADD COLUMN IF NOT EXISTS authenticated BOOLEAN NOT NULL DEFAULT false"),
    ("beh_button_click", "ALTER TABLE beh_button_click ADD COLUMN IF NOT EXISTS authenticated BOOLEAN NOT NULL DEFAULT false"),
    ("beh_auth_attempt", "ALTER TABLE beh_auth_attempt ADD COLUMN IF NOT EXISTS authenticated BOOLEAN NOT NULL DEFAULT false"),
)


def upgrade():
    connection = op.get_bind()
    inspector = inspect(connection)
    for table_name, statement in UPGRADES:
        if inspector.has_table(table_name):
            connection.execute(text(statement))

    inspector = inspect(connection)
    quote = connection.dialect.identifier_preparer.quote
    for table in db.metadata.sorted_tables:
        if not table.name.startswith("stix_") or not inspector.has_table(table.name):
            continue
        for column in inspector.get_columns(table.name):
            if isinstance(column["type"], Boolean) and column["name"] not in table.c:
                connection.execute(text(
                    f"ALTER TABLE {quote(table.name)} DROP COLUMN {quote(column['name'])}"
                ))
        if table.name != StixIndicator.__tablename__ and "raw" in table.c:
            connection.execute(text(
                f"UPDATE {quote(table.name)} SET raw = raw - 'revoked' WHERE raw ? 'revoked'"
            ))


def downgrade():
    raise RuntimeError("The schema adoption migration is irreversible; restore from backup to downgrade")

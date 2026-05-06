"""
STIX 2.1 observable / SDO storage.

Each STIX object type has its own table.  Common columns:
  - id              local PK (int)
  - stix_id         STIX canonical id (e.g. "ipv4-addr--<uuid>"), unique
  - value           human-readable representative value (indexed)
  - created_at_platform  when first seen on this platform
  - last_refreshed_at    when last enriched from an external source
  - decayed         True once data is older than INTEL_DECAY_DAYS
  - raw             full STIX object as JSONB
"""

from services.database import db
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import func


class _StixBase:
    """Mixin providing common columns for STIX-backed tables."""
    id = db.Column(db.Integer, primary_key=True)
    stix_id = db.Column(db.String(128), unique=True, nullable=False, index=True)
    value = db.Column(db.String(2048), nullable=False, index=True)
    created_at_platform = db.Column(db.DateTime, server_default=func.now(), nullable=False)
    last_refreshed_at = db.Column(db.DateTime, nullable=True)
    decayed = db.Column(db.Boolean, default=False, nullable=False)
    raw = db.Column(JSONB, nullable=False, default=dict)
    source_connector_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "stix_id": self.stix_id,
            "value": self.value,
            "created_at_platform": self.created_at_platform.isoformat() if self.created_at_platform else None,
            "last_refreshed_at": self.last_refreshed_at.isoformat() if self.last_refreshed_at else None,
            "decayed": self.decayed,
            "raw": self.raw or {},
            "source_connector_id": self.source_connector_id,
        }

    def __str__(self):
        return f"{self.__class__.__name__}({self.value})"


class StixIPv4Addr(_StixBase, db.Model):
    __tablename__ = "stix_ipv4_addr"


class StixIPv6Addr(_StixBase, db.Model):
    __tablename__ = "stix_ipv6_addr"


class StixUserAgent(_StixBase, db.Model):
    __tablename__ = "stix_user_agent"


class StixAutonomousSystem(_StixBase, db.Model):
    __tablename__ = "stix_autonomous_system"
    # `value` holds the AS number as string; name kept in raw.


class StixCountry(_StixBase, db.Model):
    """STIX 2.1 location SDO scoped to country.  `value` = ISO country code."""
    __tablename__ = "stix_country"


class StixIndicator(_StixBase, db.Model):
    __tablename__ = "stix_indicator"
    # `value` holds the indicator pattern (truncated if needed).


class StixMalware(_StixBase, db.Model):
    __tablename__ = "stix_malware"
    # `value` holds the malware name.


class StixCampaign(_StixBase, db.Model):
    __tablename__ = "stix_campaign"
    # `value` holds the campaign name.


class StixIntrusionSet(_StixBase, db.Model):
    __tablename__ = "stix_intrusion_set"
    # `value` holds the intrusion-set name.


class StixRelationship(db.Model):
    """
    STIX 2.1 relationship SRO between two STIX objects identified by stix_id.

    Source/target are referenced by their STIX id (string) rather than a
    foreign-key, because they may live in different tables.
    """
    __tablename__ = "stix_relationship"

    id = db.Column(db.Integer, primary_key=True)
    stix_id = db.Column(db.String(128), unique=True, nullable=False, index=True)
    relationship_type = db.Column(db.String(64), nullable=False, index=True)
    source_ref = db.Column(db.String(128), nullable=False, index=True)
    target_ref = db.Column(db.String(128), nullable=False, index=True)
    created_at_platform = db.Column(db.DateTime, server_default=func.now(), nullable=False)
    start_time = db.Column(db.DateTime, nullable=True)
    stop_time = db.Column(db.DateTime, nullable=True)
    decayed = db.Column(db.Boolean, default=False, nullable=False)
    raw = db.Column(JSONB, nullable=False, default=dict)
    source_connector_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "stix_id": self.stix_id,
            "relationship_type": self.relationship_type,
            "source_ref": self.source_ref,
            "target_ref": self.target_ref,
            "created_at_platform": self.created_at_platform.isoformat() if self.created_at_platform else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "stop_time": self.stop_time.isoformat() if self.stop_time else None,
            "decayed": self.decayed,
            "raw": self.raw or {},
            "source_connector_id": self.source_connector_id,
        }

    def __str__(self):
        return f"StixRelationship({self.relationship_type}: {self.source_ref} -> {self.target_ref})"

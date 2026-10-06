"""Network-related STIX SCO tables."""

from services.database import db

from models.stix.base import StixObjectBase


class StixIPv4Addr(StixObjectBase, db.Model):
    __tablename__ = "stix_ipv4_addr"


class StixIPv6Addr(StixObjectBase, db.Model):
    __tablename__ = "stix_ipv6_addr"


class StixAutonomousSystem(StixObjectBase, db.Model):
    __tablename__ = "stix_autonomous_system"


class StixUserAgent(StixObjectBase, db.Model):
    """OpenCTI-compatible user-agent SCO extension used by OFM."""
    __tablename__ = "stix_user_agent"
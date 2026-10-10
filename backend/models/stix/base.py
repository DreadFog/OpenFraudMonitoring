"""Shared persistence fields for typed STIX object tables."""

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSONB

from services.database import db


class StixObjectBase:
    id = db.Column(db.Integer, primary_key=True)
    stix_id = db.Column(db.String(128), unique=True, nullable=False, index=True)
    value = db.Column(db.String(2048), nullable=False, index=True)
    created_at_platform = db.Column(db.DateTime, server_default=func.now(), nullable=False)
    last_refreshed_at = db.Column(db.DateTime, nullable=True)
    raw = db.Column(JSONB, nullable=False, default=dict)
    source_connector_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    def to_dict(self):
        stix_object = self.raw or {}
        created_at_platform = self.created_at_platform.isoformat() if self.created_at_platform else None
        last_refreshed_at = self.last_refreshed_at.isoformat() if self.last_refreshed_at else None
        platform = {
            "id": self.id,
            "created_at_platform": created_at_platform,
            "last_refreshed_at": last_refreshed_at,
            "source_connector_id": self.source_connector_id,
        }
        return {
            "id": self.id,
            "stix_type": stix_object.get("type"),
            "stix_id": self.stix_id,
            "value": self.value,
            "created_at_platform": created_at_platform,
            "last_refreshed_at": last_refreshed_at,
            "raw": stix_object,
            "source_connector_id": self.source_connector_id,
            "stix_object": stix_object,
            "platform": platform,
        }

    def __str__(self):
        return f"{self.__class__.__name__}({self.value})"
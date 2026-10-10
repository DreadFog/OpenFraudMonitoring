"""STIX generic Relationship SRO table."""

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSONB

from services.database import db


class StixRelationship(db.Model):
    __tablename__ = "stix_relationship"

    id = db.Column(db.Integer, primary_key=True)
    stix_id = db.Column(db.String(128), unique=True, nullable=False, index=True)
    relationship_type = db.Column(db.String(64), nullable=False, index=True)
    source_ref = db.Column(db.String(128), nullable=False, index=True)
    target_ref = db.Column(db.String(128), nullable=False, index=True)
    created_at_platform = db.Column(db.DateTime, server_default=func.now(), nullable=False)
    start_time = db.Column(db.DateTime, nullable=True)
    stop_time = db.Column(db.DateTime, nullable=True)
    raw = db.Column(JSONB, nullable=False, default=dict)
    source_connector_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    def to_dict(self):
        stix_object = self.raw or {}
        created_at_platform = self.created_at_platform.isoformat() if self.created_at_platform else None
        start_time = stix_object.get("start_time")
        stop_time = stix_object.get("stop_time")
        return {
            "id": self.id,
            "stix_type": "relationship",
            "stix_id": self.stix_id,
            "relationship_type": self.relationship_type,
            "source_ref": self.source_ref,
            "target_ref": self.target_ref,
            "created_at_platform": created_at_platform,
            "start_time": start_time,
            "stop_time": stop_time,
            "raw": stix_object,
            "source_connector_id": self.source_connector_id,
            "stix_object": stix_object,
            "platform": {
                "id": self.id,
                "created_at_platform": created_at_platform,
                "source_connector_id": self.source_connector_id,
            },
        }

    def __str__(self):
        return f"StixRelationship({self.relationship_type}: {self.source_ref} -> {self.target_ref})"
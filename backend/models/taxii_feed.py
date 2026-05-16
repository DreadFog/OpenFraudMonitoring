"""TAXII feed configuration model."""

import uuid

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSONB

from services.database import db


class TaxiiFeed(db.Model):
    __tablename__ = "taxii_feeds"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    object_types = db.Column(JSONB, nullable=False, default=list)
    filters = db.Column(JSONB, nullable=False, default=list)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "uuid": self.uuid,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "object_types": list(self.object_types or []),
            "filters": list(self.filters or []),
            "owner_user_id": self.owner_user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

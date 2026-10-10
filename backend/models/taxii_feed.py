"""CSV and TAXII feed configuration with durable incremental CSV batches."""

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
    is_public = db.Column(db.Boolean, nullable=False, default=False)
    export_format = db.Column(db.String(8), nullable=False, default="taxii")
    export_fields = db.Column(JSONB, nullable=False, default=list)
    include_headers = db.Column(db.Boolean, nullable=False, default=True)
    csv_delimiter = db.Column(db.String(1), nullable=False, default=",")
    auto_update = db.Column(db.Boolean, nullable=False, default=False)
    update_interval_minutes = db.Column(db.Integer, nullable=False, default=60)
    filter_logic = db.Column(db.String(3), nullable=False, default="AND")
    matching_ids = db.Column(JSONB, nullable=False, default=list)
    csv_content = db.Column(db.Text, nullable=True)
    last_generated_at = db.Column(db.DateTime, nullable=True)
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
            "is_public": self.is_public,
            "export_format": self.export_format,
            "export_fields": list(self.export_fields or []),
            "include_headers": self.include_headers,
            "csv_delimiter": self.csv_delimiter,
            "auto_update": self.auto_update,
            "update_interval_minutes": self.update_interval_minutes,
            "filter_logic": self.filter_logic,
            "last_generated_at": self.last_generated_at.isoformat() if self.last_generated_at else None,
            "object_types": list(self.object_types or []),
            "filters": list(self.filters or []),
            "owner_user_id": self.owner_user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

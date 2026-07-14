"""
Global (instance-wide) application settings stored as key/value pairs.

Used for admin-managed configuration that must be editable at runtime and
shared across all users — e.g. the graph expansion warning threshold.
"""

from services.database import db
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSONB


class AppSetting(db.Model):
    __tablename__ = "app_settings"

    key = db.Column(db.String(128), primary_key=True)
    value = db.Column(JSONB, nullable=False, default=dict)
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self):
        return {
            "key": self.key,
            "value": self.value,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<AppSetting {self.key}>"

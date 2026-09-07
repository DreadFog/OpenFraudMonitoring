from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSONB

from services.database import db


class DomainConfig(db.Model):
    __tablename__ = "domain_configs"

    id = db.Column(db.Integer, primary_key=True)
    domain = db.Column(db.String(255), unique=True, nullable=False, index=True)
    auth_cookie_name = db.Column(db.String(255), nullable=True)
    form_action = db.Column(db.String(2048), nullable=True)
    form_method = db.Column(db.String(16), nullable=False, default="post")
    form_field_names = db.Column(JSONB, nullable=False, default=list)
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "domain": self.domain,
            "auth_cookie_name": self.auth_cookie_name or "",
            "form_action": self.form_action or "",
            "form_method": self.form_method or "post",
            "form_field_names": self.form_field_names or [],
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

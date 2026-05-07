"""
CORS allowed origins model.
"""

from datetime import datetime
from services.database import db


class AllowedOrigin(db.Model):
    __tablename__ = "allowed_origins"
    
    id = db.Column(db.Integer, primary_key=True)
    origin = db.Column(db.String(255), unique=True, nullable=False, index=True)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "origin": self.origin,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

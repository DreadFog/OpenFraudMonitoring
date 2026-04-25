from services.database import db
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import func


class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(512), unique=True, nullable=False, index=True)
    risk_score = db.Column(db.Integer, default=0)
    flags = db.Column(JSONB, default=list)
    client_ip = db.Column(db.String(45), default="")
    first_seen = db.Column(db.Float, default=0)
    last_seen = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())

    fingerprints = db.relationship("Fingerprint", back_populates="session", lazy="dynamic")
    heartbeats = db.relationship("Heartbeat", back_populates="session", lazy="dynamic")
    urls = db.relationship("SessionURL", back_populates="session", lazy="dynamic")
    browser_sessions = db.relationship("BrowserSession", back_populates="session", lazy="dynamic")

    def to_dict(self):
        return {
            "device_id": self.device_id,
            "risk_score": self.risk_score,
            "flags": self.flags or [],
            "client_ip": self.client_ip,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }

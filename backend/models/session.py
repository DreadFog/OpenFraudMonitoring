from services.database import db
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import func


class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    fsid = db.Column(db.String(512), unique=True, nullable=False, index=True)
    risk_score = db.Column(db.Integer, default=0)
    flags = db.Column(JSONB, default=list)
    client_ip = db.Column(db.String(45), default="")
    # ── STIX observable links (Phase 1) ──
    # IP can be either ipv4 or ipv6; track the type to know which table
    # to look up in.  `None` if no STIX observable was created.
    ip_observable_type = db.Column(db.String(16), nullable=True)  # 'ipv4-addr' | 'ipv6-addr'
    ip_observable_id = db.Column(db.Integer, nullable=True)
    user_agent_observable_id = db.Column(db.Integer, nullable=True)
    first_seen = db.Column(db.Float, default=0)
    last_seen = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())

    fingerprints = db.relationship("Fingerprint", back_populates="session", lazy="dynamic", cascade="all, delete-orphan")
    heartbeats = db.relationship("Heartbeat", back_populates="session", lazy="dynamic", cascade="all, delete-orphan")
    behavioral_events = db.relationship("BehavioralEvent", back_populates="session", lazy="dynamic", cascade="all, delete-orphan")
    urls = db.relationship("SessionURL", back_populates="session", lazy="dynamic", cascade="all, delete-orphan")
    browser_sessions = db.relationship("BrowserSession", back_populates="session", lazy="dynamic", cascade="all, delete-orphan")
    rule_matches = db.relationship("RuleMatch", lazy="dynamic", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "fsid": self.fsid,
            "risk_score": self.risk_score,
            "flags": self.flags or [],
            "client_ip": self.client_ip,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }

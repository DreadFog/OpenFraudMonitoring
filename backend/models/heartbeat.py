from services.database import db
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import func


class Heartbeat(db.Model):
    __tablename__ = "heartbeats"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    timestamp = db.Column(db.Float, default=0)
    url = db.Column(db.String(2048), default="")
    mouse_moves = db.Column(db.Integer, default=0)
    clicks = db.Column(db.Integer, default=0)
    keydowns = db.Column(db.Integer, default=0)
    touches = db.Column(db.Integer, default=0)
    scrolls = db.Column(db.Integer, default=0)
    raw_behavior = db.Column(JSONB, default=dict)
    created_at = db.Column(db.DateTime, server_default=func.now())

    session = db.relationship("Session", back_populates="heartbeats")

    def to_summary(self):
        return {
            "timestamp": self.timestamp,
            "url": self.url,
            "mouseMoves": self.mouse_moves,
            "clicks": self.clicks,
            "keydowns": self.keydowns,
            "touches": self.touches,
            "scrolls": self.scrolls,
            "raw": self.raw_behavior,
        }

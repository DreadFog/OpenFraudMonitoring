from services.database import db
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import func


class BehavioralEvent(db.Model):
    __tablename__ = "behavioral_events"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    timestamp = db.Column(db.Float, default=0)
    url = db.Column(db.String(2048), default="")
    event_type = db.Column(db.String(64), default="", index=True)  # "button_click", "form_submit", "copy", "paste"
    data = db.Column(JSONB, default=dict)
    created_at = db.Column(db.DateTime, server_default=func.now())

    session = db.relationship("Session", back_populates="behavioral_events")

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "url": self.url,
            "event_type": self.event_type,
            "data": self.data or {},
        }

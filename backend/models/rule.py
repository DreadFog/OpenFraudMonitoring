from services.database import db
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import func


class Rule(db.Model):
    __tablename__ = "rules"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, default="")
    enabled = db.Column(db.Boolean, default=True)
    rule_type = db.Column(db.String(16), default="realtime")  # realtime | periodic
    logic = db.Column(db.String(4), default="AND")            # AND | OR
    conditions = db.Column(JSONB, nullable=False)
    score_modifier = db.Column(db.Integer, default=0)
    period_seconds = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "rule_type": self.rule_type,
            "logic": self.logic,
            "conditions": self.conditions or [],
            "score_modifier": self.score_modifier,
            "period_seconds": self.period_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RuleMatch(db.Model):
    __tablename__ = "rule_matches"

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("rules.id"), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    matched_at = db.Column(db.DateTime, server_default=func.now())
    score_change = db.Column(db.Integer, default=0)

    rule = db.relationship("Rule")
    session = db.relationship("Session")

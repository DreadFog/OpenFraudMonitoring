"""
Typed behavioral event models — one table per high-signal event type.

Replaces the previous single `behavioral_events` table (which stored all event
data as an opaque JSONB blob).  The old table is left untouched in the DB so
that existing data is not lost, but new events are written exclusively to these
typed tables.

Tables:
    beh_copy          — copy events
    beh_paste         — paste events
    beh_form_submit   — form submit events
    beh_button_click  — button click events
    beh_auth_attempt  — form submissions matching a configured login pattern

The legacy BehavioralEvent model is kept for backward-compatible imports but
is no longer written to by the ingestion route.
"""

from services.database import db
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import func, Index


# ─────────────────────────────────────────────────────────────────────────────
# Legacy model (deprecated — kept for backward-compatible imports only)
# ─────────────────────────────────────────────────────────────────────────────

class BehavioralEvent(db.Model):
    __tablename__ = "behavioral_events"
    __table_args__ = (
        db.Index("ix_behavioral_events_session_event_type", "session_id", "event_type"),
        db.Index("ix_behavioral_events_event_type_timestamp", "event_type", "timestamp"),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    timestamp = db.Column(db.Float, default=0)
    url = db.Column(db.String(2048), default="")
    event_type = db.Column(db.String(64), default="", index=True)
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


# ─────────────────────────────────────────────────────────────────────────────
# Typed models
# ─────────────────────────────────────────────────────────────────────────────

class CopyEvent(db.Model):
    """A copy event — text was selected and copied from the page."""
    __tablename__ = "beh_copy"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    timestamp = db.Column(db.Float, default=0, nullable=False)
    url = db.Column(db.String(2048), default="")
    created_at = db.Column(db.DateTime, server_default=func.now())

    # Content
    length = db.Column(db.Integer, default=0)
    text = db.Column(db.Text, nullable=True)  # only when captureClipboard=true

    # DOM context of the element that had focus at copy time
    source_tag = db.Column(db.String(64), default="")
    source_id = db.Column(db.String(256), default="")
    source_name = db.Column(db.String(256), default="")
    source_type = db.Column(db.String(64), default="")
    form_action = db.Column(db.String(2048), default="")

    session = db.relationship("Session")

    EVENT_TYPE = "copy"

    def to_dict(self):
        d = {
            "event_type": self.EVENT_TYPE,
            "timestamp": self.timestamp,
            "url": self.url,
            "length": self.length,
            "source_tag": self.source_tag,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "form_action": self.form_action,
        }
        if self.text is not None:
            d["text"] = self.text
        return d


class PasteEvent(db.Model):
    """A paste event — text was pasted into a focused element."""
    __tablename__ = "beh_paste"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    timestamp = db.Column(db.Float, default=0, nullable=False)
    url = db.Column(db.String(2048), default="")
    created_at = db.Column(db.DateTime, server_default=func.now())

    # Content
    length = db.Column(db.Integer, default=0)
    text = db.Column(db.Text, nullable=True)  # only when captureClipboard=true

    # DOM context of the element that received the paste
    target_tag = db.Column(db.String(64), default="")
    target_id = db.Column(db.String(256), default="")
    target_name = db.Column(db.String(256), default="", index=True)
    target_type = db.Column(db.String(64), default="")
    form_action = db.Column(db.String(2048), default="")

    session = db.relationship("Session")

    EVENT_TYPE = "paste"

    def to_dict(self):
        d = {
            "event_type": self.EVENT_TYPE,
            "timestamp": self.timestamp,
            "url": self.url,
            "length": self.length,
            "target_tag": self.target_tag,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "target_type": self.target_type,
            "form_action": self.form_action,
        }
        if self.text is not None:
            d["text"] = self.text
        return d


class FormSubmitEvent(db.Model):
    """A form submission event."""
    __tablename__ = "beh_form_submit"
    __table_args__ = (
        Index("ix_beh_form_submit_field_names", "field_names", postgresql_using="gin"),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    timestamp = db.Column(db.Float, default=0, nullable=False)
    url = db.Column(db.String(2048), default="")
    created_at = db.Column(db.DateTime, server_default=func.now())

    action = db.Column(db.String(2048), default="")
    method = db.Column(db.String(16), default="")
    # Variable-length array of field names — kept as JSONB with a GIN index.
    field_names = db.Column(JSONB, default=list)

    session = db.relationship("Session")

    EVENT_TYPE = "form_submit"

    def to_dict(self):
        return {
            "event_type": self.EVENT_TYPE,
            "timestamp": self.timestamp,
            "url": self.url,
            "action": self.action,
            "method": self.method,
            "field_names": self.field_names or [],
        }


class ButtonClickEvent(db.Model):
    """A button or submit-role element click event."""
    __tablename__ = "beh_button_click"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    timestamp = db.Column(db.Float, default=0, nullable=False)
    url = db.Column(db.String(2048), default="")
    created_at = db.Column(db.DateTime, server_default=func.now())

    x = db.Column(db.Integer, nullable=True)
    y = db.Column(db.Integer, nullable=True)
    tag = db.Column(db.String(64), default="")
    text = db.Column(db.String(512), default="")

    session = db.relationship("Session")

    EVENT_TYPE = "button_click"

    def to_dict(self):
        return {
            "event_type": self.EVENT_TYPE,
            "timestamp": self.timestamp,
            "url": self.url,
            "x": self.x,
            "y": self.y,
            "tag": self.tag,
            "text": self.text,
        }


class AuthAttemptEvent(db.Model):
    """A form submission matching a monitored domain's auth pattern."""
    __tablename__ = "beh_auth_attempt"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    domain_config_id = db.Column(db.Integer, db.ForeignKey("domain_configs.id", ondelete="SET NULL"), nullable=True, index=True)
    timestamp = db.Column(db.Float, default=0, nullable=False)
    url = db.Column(db.String(2048), default="")
    created_at = db.Column(db.DateTime, server_default=func.now())
    action = db.Column(db.String(2048), default="")
    method = db.Column(db.String(16), default="post")
    matched_field_names = db.Column(JSONB, default=list)

    session = db.relationship("Session")
    domain_config = db.relationship("DomainConfig")

    EVENT_TYPE = "auth_attempt"

    def to_dict(self):
        return {
            "event_type": self.EVENT_TYPE,
            "timestamp": self.timestamp,
            "url": self.url,
            "action": self.action,
            "method": self.method,
            "matched_field_names": self.matched_field_names or [],
        }


# Map event_type string → typed model class, used by the ingestion route and
# the sequence rule evaluator.
TYPED_EVENT_MODELS = {
    "copy": CopyEvent,
    "paste": PasteEvent,
    "form_submit": FormSubmitEvent,
    "button_click": ButtonClickEvent,
    "auth_attempt": AuthAttemptEvent,
}

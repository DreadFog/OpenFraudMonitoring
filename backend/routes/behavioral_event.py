"""
Behavioral Event endpoint — receives direct behavioral events (button clicks, form submits, copy/paste).

Expected payload:
  {
    "fsid": "<session_fingerprint_id>",
    "timestamp": 1234567890,
    "url": "https://...",
    "event_type": "button_click|form_submit|copy|paste",
    "data": { ... }  # event-specific data
  }
"""

import logging
from flask import Blueprint, request, jsonify
from services.database import db
from models import Session, BehavioralEvent
from services.event_queue import enqueue_event

logger = logging.getLogger(__name__)

behavioral_event_bp = Blueprint("behavioral_event", __name__, url_prefix="/api")

# Allowed event types
ALLOWED_EVENT_TYPES = {"button_click", "form_submit", "copy", "paste"}


@behavioral_event_bp.route("/behavioral_event", methods=["POST"])
def behavioral_event():
    """
    Receive and store a behavioral event.
    """
    payload = request.get_json() or {}

    fsid = payload.get("fsid")
    timestamp = payload.get("timestamp", 0)
    url = payload.get("url", "")
    event_type = payload.get("event_type", "")
    data = payload.get("data", {})

    # Validate event_type
    if event_type not in ALLOWED_EVENT_TYPES:
        return jsonify({"ok": False, "error": f"Invalid event_type: {event_type}"}), 400

    # Find session by fsid, then IP fallback
    session_obj = None
    if fsid:
        session_obj = Session.query.filter_by(fsid=fsid).first()
    if not session_obj:
        # Fallback: find most recent session from this IP
        forwarded = request.headers.get("X-Forwarded-For", "")
        client_ip = (forwarded.split(",")[0].strip() if forwarded else "") or request.remote_addr
        session_obj = Session.query.filter_by(client_ip=client_ip).order_by(
            Session.last_seen.desc()
        ).first()

    if not session_obj:
        return jsonify({"ok": False, "error": "session not found"}), 404

    # Create and store behavioral event
    be = BehavioralEvent(
        session_id=session_obj.id,
        timestamp=timestamp,
        url=url,
        event_type=event_type,
        data=data,
    )
    db.session.add(be)
    session_obj.last_seen = timestamp
    db.session.commit()

    # Enqueue for rule evaluation (best-effort)
    enqueue_event(session_obj.id, "behavioral_event")

    logger.debug("behavioral_event: fsid=%s type=%s url=%s", fsid[:32] if fsid else "", event_type, url)

    return jsonify({"ok": True}), 200

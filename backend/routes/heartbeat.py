"""
Heartbeat endpoint — receives periodic extension drain data (behavior, etc.)

Expected payload:
  {
    "visit_id": "<per-tab-visit-uuid>",
    "timestamp": 1234567890,
    "url": "https://...",
    "extensions": {
      "behavior": { "mouseMoves": [...], "clicks": [...], ... }
    }
  }
"""

from flask import Blueprint, request, jsonify
from services.database import db
from models import Session, Heartbeat, SessionURL
from utils import extract_behavior_summary
from services.event_queue import enqueue_event
from services.domains import add_session_domain, auth_cookie_present
from services.visit_identity import normalize_visit_id
import logging

logger = logging.getLogger(__name__)
heartbeat_bp = Blueprint("heartbeat", __name__, url_prefix="/api")

@heartbeat_bp.route("/heartbeat", methods=["POST"])
def heartbeat():
    """
    Receive periodic heartbeat with extension drain data.

    The heartbeat is linked to the visit token established by initial collection.
    """
    hb = request.get_json() or {}

    url = hb.get("url", "")
    timestamp = hb.get("timestamp", 0)
    extensions = hb.get("extensions", {})
    behavior = extensions.get("behavior", {})

    visit_id = normalize_visit_id(hb.get("visit_id"))
    if visit_id is None:
        return jsonify({"ok": False, "error": "visit_id must be a UUID"}), 400
    session_obj = Session.query.filter_by(visit_id=visit_id).first()

    if not session_obj:
        return jsonify({"ok": False, "error": "visit not found"}), 404

    # Extract behavior summary
    behavior_summary = extract_behavior_summary(behavior)

    # Store heartbeat with denormalized counts
    hb_record = Heartbeat(
        session_id=session_obj.id,
        timestamp=timestamp,
        url=url,
        mouse_moves=behavior_summary["mouseMoves"],
        clicks=behavior_summary["clicks"],
        keydowns=behavior_summary["keydowns"],
        touches=behavior_summary["touches"],
        scrolls=behavior_summary["scrolls"],
        raw_behavior=behavior,
        authenticated=auth_cookie_present(request, request.host),
    )
    db.session.add(hb_record)

    # Update session
    session_obj.last_seen = timestamp
    session_obj.authenticated = hb_record.authenticated
    add_session_domain(session_obj, url)
    logger.debug(
        "session authentication state: fsid=%s host=%s authenticated=%s",
        session_obj.fsid[:32], request.host, session_obj.authenticated,
    )

    # Track URL
    if url:
        existing_url = SessionURL.query.filter_by(
            session_id=session_obj.id, url=url
        ).first()
        if not existing_url:
            db.session.add(SessionURL(session_id=session_obj.id, url=url))

    db.session.commit()

    # Enqueue for rule evaluation (best-effort)
    enqueue_event(session_obj.id, "heartbeat")

    print(f"[HEARTBEAT] fsid={session_obj.fsid[:32]} url={url} moves={behavior_summary['mouseMoves']} clicks={behavior_summary['clicks']}")

    return jsonify({"ok": True}), 200

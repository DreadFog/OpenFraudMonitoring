"""
Heartbeat endpoint - receives behavioral updates
"""

from flask import Blueprint, request, jsonify
from services.database import db
from models import Session, Heartbeat, SessionURL, BrowserSession
from utils import extract_behavior_summary
from services.event_queue import enqueue_event

heartbeat_bp = Blueprint("heartbeat", __name__, url_prefix="/api")


@heartbeat_bp.route("/heartbeat", methods=["POST"])
def heartbeat():
    """
    Receive behavioral heartbeat updates
    """
    hb = request.get_json() or {}

    session_id = hb.get("session", "unknown")
    url = hb.get("url", "")
    timestamp = hb.get("timestamp", 0)
    behavior = hb.get("behavior", {})

    # Find session by browser session ID
    browser_sess = BrowserSession.query.filter_by(
        browser_session_id=session_id
    ).first()
    if not browser_sess:
        return jsonify({"ok": False, "error": "session not found"}), 404

    session_obj = Session.query.get(browser_sess.session_id)
    if not session_obj:
        return jsonify({"ok": False, "error": "session not found"}), 404

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
        copy_pastes=behavior_summary["copyPastes"],
        navigation_events=behavior_summary["navigationEvents"],
        raw_behavior=behavior,
    )
    db.session.add(hb_record)

    # Update session
    session_obj.last_seen = timestamp

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

    print(f"[HEARTBEAT] device_id={session_obj.device_id[:16]} url={url} moves={behavior_summary['mouseMoves']} clicks={behavior_summary['clicks']}")

    return jsonify({"ok": True}), 200

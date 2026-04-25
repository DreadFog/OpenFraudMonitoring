"""
Collect endpoint - receives initial fingerprints on page load
"""

from flask import Blueprint, request, jsonify
from services.database import db
from models import Session, Fingerprint, SessionURL, BrowserSession
from services.event_queue import enqueue_event

collect_bp = Blueprint("collect", __name__, url_prefix="/api")


@collect_bp.route("/collect", methods=["POST"])
def collect():
    """
    Receive and store initial fingerprint
    """
    fp = request.get_json() or {}

    device_id = fp.get("deviceID", "unknown")
    session_id = fp.get("session", "unknown")
    url = fp.get("url", "")
    timestamp = fp.get("timestamp", 0)

    # Get client IP
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)

    # Find or create session (score starts at 0, rules adjust it via the worker)
    session_obj = Session.query.filter_by(device_id=device_id).first()
    if not session_obj:
        session_obj = Session(device_id=device_id, first_seen=timestamp)
        db.session.add(session_obj)
        db.session.flush()

    session_obj.last_seen = timestamp
    session_obj.client_ip = client_ip

    # Store fingerprint with denormalized fields
    denorm = Fingerprint.extract_fields(fp)
    fingerprint = Fingerprint(
        session_id=session_obj.id,
        timestamp=timestamp,
        data=fp,
        **denorm,
    )
    db.session.add(fingerprint)

    # Track URL (ignore duplicate)
    existing_url = SessionURL.query.filter_by(
        session_id=session_obj.id, url=url
    ).first()
    if not existing_url and url:
        db.session.add(SessionURL(session_id=session_obj.id, url=url))

    # Track browser session ID
    existing_bs = BrowserSession.query.filter_by(
        browser_session_id=session_id
    ).first()
    if not existing_bs:
        db.session.add(BrowserSession(
            session_id=session_obj.id,
            browser_session_id=session_id,
        ))

    db.session.commit()

    # Enqueue for rule evaluation (best-effort)
    enqueue_event(session_obj.id, "fingerprint")

    print(f"[COLLECT] device_id={device_id[:16]} url={url}")

    return jsonify({
        "ok": True,
        "device_id": device_id,
        "session_id": session_id,
    }), 200

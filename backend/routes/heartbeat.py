"""
Heartbeat endpoint — receives periodic extension drain data (behavior, etc.)

Expected payload:
  {
    "timestamp": 1234567890,
    "url": "https://...",
    "extensions": {
      "behavior": { "mouseMoves": [...], "clicks": [...], ... }
    }
  }
"""

from flask import Blueprint, request, jsonify, current_app
from services.database import db
from models import Session, Heartbeat, SessionURL
from utils import extract_behavior_summary
from services.event_queue import enqueue_event
from services.domains import add_session_domain, auth_cookie_present
import logging
import ipaddress

logger = logging.getLogger(__name__)
heartbeat_bp = Blueprint("heartbeat", __name__, url_prefix="/api")

PRIVATE_CIDRS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
]

def _is_private_ip(ip_value: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip_value)
    except ValueError:
        return False
    return any(ip_obj in cidr for cidr in PRIVATE_CIDRS)

@heartbeat_bp.route("/heartbeat", methods=["POST"])
def heartbeat():
    """
    Receive periodic heartbeat with extension drain data.

    The heartbeat is linked to a session via the fsid provided
    in the most recent collect call (stored server-side).
    For now, the client doesn't send fsid in heartbeats — we use
    the client IP + most recent session as a fallback.
    """
    hb = request.get_json() or {}

    url = hb.get("url", "")
    timestamp = hb.get("timestamp", 0)
    extensions = hb.get("extensions", {})
    behavior = extensions.get("behavior", {})

    # Find session — use fsid if provided, otherwise fall back to client IP
    fsid = hb.get("fsid")
    session_obj = None
    if fsid:
        session_obj = Session.query.filter_by(fsid=fsid).first()
    if not session_obj:
        # Fallback: find most recent session from this IP
        forwarded = request.headers.get("X-Forwarded-For", "")
        client_ip = (forwarded.split(",")[0].strip() if forwarded else "") or request.remote_addr
        # If env variable set, ignore heartbeats from private IP addresses.
        save_private_ip = current_app.config.get("OFM_SAVE_PRIVATE_IP", False)
        if not save_private_ip and _is_private_ip(client_ip):
            logger.debug(f"Ignoring heartbeat from private IP {client_ip}.")
            return jsonify({"ok": True}), 200
        
        session_obj = Session.query.filter_by(client_ip=client_ip).order_by(
            Session.last_seen.desc()
        ).first()

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
        raw_behavior=behavior,
    )
    db.session.add(hb_record)

    # Update session
    session_obj.last_seen = timestamp
    session_obj.authenticated = auth_cookie_present(request, request.host)
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

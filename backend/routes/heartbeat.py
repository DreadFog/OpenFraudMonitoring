"""
Heartbeat endpoint - receives behavioral updates
"""

from flask import Blueprint, request, jsonify
from utils import clean_old_url_entries, extract_behavior_summary
from collections import defaultdict

heartbeat_bp = Blueprint("heartbeat", __name__, url_prefix="/api")

# Shared session storage
sessions_store = {}
url_sessions_store = defaultdict(list)


def init_heartbeat_routes(app, sessions, url_sessions):
    """Initialize heartbeat routes with shared storage"""
    global sessions_store, url_sessions_store
    sessions_store = sessions
    url_sessions_store = url_sessions
    app.register_blueprint(heartbeat_bp)


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

    # Find device_id by session_id
    device_id = None
    for did, sess in sessions_store.items():
        if session_id in sess.session_ids:
            device_id = did
            break

    if not device_id:
        return jsonify({"ok": False, "error": "session not found"}), 404

    # Extract behavior summary
    behavior_summary = extract_behavior_summary(behavior)

    # Create heartbeat record
    summary = {
        "timestamp": timestamp,
        "url": url,
        **behavior_summary,
        "raw": behavior,
    }

    # Update session
    session_obj = sessions_store[device_id]
    session_obj.add_heartbeat(summary)
    session_obj.last_seen = timestamp

    # Track URL
    if url:
        session_obj.urls.add(url)
        url_sessions_store[device_id].append({"url": url, "timestamp": timestamp})
        clean_old_url_entries(url_sessions_store, device_id)

    print(f"[HEARTBEAT] device_id={device_id[:16]} url={url} moves={behavior_summary['mouseMoves']} clicks={behavior_summary['clicks']}")

    return jsonify({"ok": True}), 200

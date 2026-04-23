"""
Sessions endpoints - list and detail views
"""

from flask import Blueprint, jsonify
from utils import get_time_ago_string

sessions_bp = Blueprint("sessions", __name__, url_prefix="/api")

# Shared session storage
sessions_store = {}


def init_sessions_routes(app, sessions):
    """Initialize sessions routes with shared storage"""
    global sessions_store
    sessions_store = sessions
    app.register_blueprint(sessions_bp)


@sessions_bp.route("/sessions", methods=["GET"])
def get_sessions():
    """
    Get all sessions with basic info
    """
    sessions_list = []

    for device_id, sess in sessions_store.items():
        fps = sess.fingerprints
        last_fp = fps[-1] if fps else {}
        nav = last_fp.get("navigator", {})

        sessions_list.append({
            "device_id": device_id[:16] + "..." if len(device_id) > 16 else device_id,
            "full_device_id": device_id,
            "client_ip": sess.client_ip or "unknown",
            "risk_score": sess.risk_score,
            "flags": sess.flags[:5],
            "first_seen": sess.first_seen,
            "last_seen": sess.last_seen,
            "heartbeats": len(sess.heartbeats),
            "urls": list(sess.urls)[:3],
            "user_agent": nav.get("userAgent", "unknown")[:60],
            "platform": nav.get("platform", "unknown"),
            "is_workstation": nav.get("isWorkstation", False),
            "is_mobile": nav.get("isMobile", False),
            "language": nav.get("language", "unknown"),
            "urls_count": len(sess.urls),
            "session_ids": list(sess.session_ids)[:2],
        })

    # Sort by risk score descending
    sessions_list.sort(key=lambda x: x["risk_score"], reverse=True)

    return jsonify(sessions_list), 200


@sessions_bp.route("/sessions/<device_id>", methods=["GET"])
def get_session_detail(device_id):
    """
    Get detailed session information
    """
    sess = sessions_store.get(device_id)
    if not sess:
        return jsonify({"error": "session not found"}), 404

    return jsonify({
        "device_id": device_id,
        "client_ip": sess.client_ip,
        "risk_score": sess.risk_score,
        "flags": sess.flags,
        "first_seen": sess.first_seen,
        "last_seen": sess.last_seen,
        "urls": list(sess.urls),
        "session_ids": list(sess.session_ids),
        "heartbeats_count": len(sess.heartbeats),
        "fingerprints_count": len(sess.fingerprints),
        "latest_fingerprint": sess.fingerprints[-1] if sess.fingerprints else None,
        "heartbeats": sess.heartbeats[:20],
    }), 200

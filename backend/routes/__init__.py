"""
Collect endpoint - receives initial fingerprints on page load
"""

from flask import Blueprint, request, jsonify
from analysis import RiskAnalyzer
from utils import clean_old_url_entries, format_fingerprint_summary
from collections import defaultdict

collect_bp = Blueprint("collect", __name__, url_prefix="/api")

# Shared session storage (passed from main app)
sessions_store = {}
url_sessions_store = defaultdict(list)


def init_collect_routes(app, sessions, url_sessions):
    """Initialize collect routes with shared storage"""
    global sessions_store, url_sessions_store
    sessions_store = sessions
    url_sessions_store = url_sessions
    app.register_blueprint(collect_bp)


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

    # Analyze fingerprint for risk
    score, flags = RiskAnalyzer.analyze(fp)

    # Track URL for this device
    url_sessions_store[device_id].append({"url": url, "timestamp": timestamp})
    clean_old_url_entries(url_sessions_store, device_id)

    # Create or update session
    if device_id not in sessions_store:
        from models import Session
        sessions_store[device_id] = Session(device_id)

    session_obj = sessions_store[device_id]
    session_obj.add_fingerprint(fp)
    session_obj.last_seen = timestamp
    session_obj.risk_score = score
    session_obj.flags = flags
    session_obj.urls.add(url)
    session_obj.session_ids.add(session_id)
    session_obj.client_ip = client_ip
    if session_obj.first_seen == 0:
        session_obj.first_seen = timestamp

    print(f"[COLLECT] device_id={device_id[:16]} url={url} risk={score} flags={','.join(flags[:3])}")

    return jsonify({
        "ok": True,
        "device_id": device_id,
        "session_id": session_id,
        "risk": score,
    }), 200

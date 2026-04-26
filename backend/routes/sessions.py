"""
Sessions endpoints - list and detail views
"""

import json
from flask import Blueprint, request, jsonify
from models import Session, Fingerprint, Heartbeat
from rules.engine import build_session_query

sessions_bp = Blueprint("sessions", __name__, url_prefix="/api")


@sessions_bp.route("/sessions", methods=["GET"])
def get_sessions():
    """
    Get all sessions with basic info.
    Accepts an optional `filters` query param (JSON array of conditions).
    """
    filters_raw = request.args.get("filters", "[]")
    try:
        filters = json.loads(filters_raw)
    except (json.JSONDecodeError, TypeError):
        filters = []

    query = build_session_query(filters)
    all_sessions = query.order_by(Session.risk_score.desc()).limit(200).all()
    sessions_list = []

    for sess in all_sessions:
        last_fp_row = sess.fingerprints.order_by(Fingerprint.timestamp.desc()).first()
        last_fp = last_fp_row.data if last_fp_row else {}
        signals = last_fp.get("signals", {})
        browser = signals.get("browser", {})
        device = signals.get("device", {})
        locale = signals.get("locale", {})
        urls = [u.url for u in sess.urls.limit(3).all()]
        urls_count = sess.urls.count()
        heartbeats_count = sess.heartbeats.count()
        session_ids = [bs.browser_session_id for bs in sess.browser_sessions.limit(2).all()]
        fsid = sess.fsid

        sessions_list.append({
            "fsid": fsid[:32] + "..." if len(fsid) > 32 else fsid,
            "full_fsid": fsid,
            "client_ip": sess.client_ip or "unknown",
            "risk_score": sess.risk_score,
            "flags": (sess.flags or [])[:5],
            "first_seen": sess.first_seen,
            "last_seen": sess.last_seen,
            "heartbeats": heartbeats_count,
            "urls": urls,
            "user_agent": str(browser.get("userAgent", "unknown"))[:60],
            "platform": str(device.get("platform", "unknown")),
            "is_mobile": bool(browser.get("highEntropyValues", {}).get("mobile")),
            "language": str(locale.get("languages", {}).get("language", "unknown")),
            "urls_count": urls_count,
            "session_ids": session_ids,
            "fast_bot_detection": last_fp.get("fastBotDetection", False),
        })

    return jsonify(sessions_list), 200


@sessions_bp.route("/sessions/<fsid>", methods=["GET"])
def get_session_detail(fsid):
    """
    Get detailed session information
    """
    sess = Session.query.filter_by(fsid=fsid).first()
    if not sess:
        return jsonify({"error": "session not found"}), 404

    urls = [u.url for u in sess.urls.all()]
    session_ids = [bs.browser_session_id for bs in sess.browser_sessions.all()]
    heartbeats_count = sess.heartbeats.count()
    fingerprints_count = sess.fingerprints.count()

    last_fp_row = sess.fingerprints.order_by(Fingerprint.timestamp.desc()).first()
    latest_fingerprint = last_fp_row.data if last_fp_row else None

    recent_heartbeats = sess.heartbeats.order_by(
        Heartbeat.timestamp.desc()
    ).limit(20).all()

    return jsonify({
        "fsid": fsid,
        "client_ip": sess.client_ip,
        "risk_score": sess.risk_score,
        "flags": sess.flags or [],
        "first_seen": sess.first_seen,
        "last_seen": sess.last_seen,
        "urls": urls,
        "session_ids": session_ids,
        "heartbeats_count": heartbeats_count,
        "fingerprints_count": fingerprints_count,
        "latest_fingerprint": latest_fingerprint,
        "heartbeats": [hb.to_summary() for hb in recent_heartbeats],
    }), 200

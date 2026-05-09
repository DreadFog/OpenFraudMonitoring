"""
Sessions endpoints - list and detail views
"""

import json
from flask import Blueprint, request, jsonify
from models import Session, Fingerprint, Heartbeat
from models.associations import SessionURL, BrowserSession
from models.rule import RuleMatch
from rules.engine import build_session_query
from services.auth import require_auth, require_role

# Platforms that are unambiguously desktop/workstation
_WORKSTATION_PLATFORMS = {
    "Win32", "Win64",
    "MacIntel", "MacPPC",
    "Linux x86_64", "Linux x86-64", "Linux aarch64",
    "Linux armv81", "Linux armv8l",
    "FreeBSD amd64",
}


def _is_workstation(device: dict, browser: dict) -> bool:
    """
    Derive workstation status from fingerprint signals.
    Signals checked (in priority order):
      1. highEntropyValues.mobile == False  → explicit non-mobile from UA-CH
      2. platform in known desktop set       → unambiguous desktop OS/arch
      3. pointer==fine AND hover==True       → mouse+hover = desktop-class input
    Returns False (not workstation) only if none match and is_mobile is True.
    """
    hev_mobile = browser.get("highEntropyValues", {}).get("mobile")
    if hev_mobile is False:
        return True

    platform = device.get("platform", "")
    if platform in _WORKSTATION_PLATFORMS:
        return True

    mq = device.get("mediaQueries", {})
    if mq.get("pointer") == "fine" and mq.get("hover") is True:
        return True

    return False


sessions_bp = Blueprint("sessions", __name__, url_prefix="/api")


@sessions_bp.route("/sessions", methods=["GET"])
@require_auth
def get_sessions():
    """
    Get paginated sessions with basic info.
    Accepts optional query params:
    - filters: JSON array of conditions
    - sort_by: 'last_seen', 'device_type', 'risk_score', 'first_seen', or 'client_ip' (default: 'last_seen')
    - sort_order: 'asc' or 'desc' (default: 'desc')
    - page: page number (default: 1)
    - per_page: results per page – 10, 25, 50 or 100 (default: 10)
    """
    filters_raw = request.args.get("filters", "[]")
    try:
        filters = json.loads(filters_raw)
    except (json.JSONDecodeError, TypeError):
        filters = []

    sort_by = request.args.get("sort_by", "last_seen")
    sort_order = request.args.get("sort_order", "desc").lower()

    try:
        page = max(1, int(request.args.get("page", "1")))
    except (ValueError, TypeError):
        page = 1

    try:
        per_page = int(request.args.get("per_page", "10"))
    except (ValueError, TypeError):
        per_page = 10
    if per_page not in (10, 25, 50, 100):
        per_page = 10
    
    query = build_session_query(filters)

    total = query.count()
    
    # Apply sorting
    if sort_by == "last_seen":
        sort_col = Session.last_seen
    elif sort_by == "first_seen":
        sort_col = Session.first_seen
    elif sort_by == "client_ip":
        sort_col = Session.client_ip
    elif sort_by == "risk_score":
        sort_col = Session.risk_score
    else:
        # Default to last_seen for 'device_type' and unknown sorts
        # (device_type is derived, so sorting will be done in post-processing)
        sort_col = Session.last_seen
    
    if sort_order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    pages = max(1, -(-total // per_page))  # ceil division
    page = min(page, pages)  # clamp to last page
    offset = (page - 1) * per_page

    page_sessions = query.offset(offset).limit(per_page).all()
    sessions_list = []

    for sess in page_sessions:
        last_fp_row = sess.fingerprints.order_by(Fingerprint.timestamp.desc()).first()
        last_fp = last_fp_row.data if last_fp_row else {}
        signals = last_fp.get("signals", {})
        browser = signals.get("browser", {})
        device = signals.get("device", {})
        locale = signals.get("locale", {})
        mq = device.get("mediaQueries", {})
        urls = [u.url for u in sess.urls.limit(3).all()]
        urls_count = sess.urls.count()
        heartbeats_count = sess.heartbeats.count()
        session_ids = [bs.browser_session_id for bs in sess.browser_sessions.limit(2).all()]
        fsid = sess.fsid
        
        is_mobile = browser.get("highEntropyValues", {}).get("mobile") is True
        is_workstation = _is_workstation(device, browser)
        device_type = "mobile" if is_mobile else ("workstation" if is_workstation else "unknown")

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
            "is_mobile": is_mobile,
            "is_workstation": is_workstation,
            "device_type": device_type,
            "language": str(locale.get("languages", {}).get("language", "unknown")),
            "urls_count": urls_count,
            "session_ids": session_ids,
            "fast_bot_detection": last_fp.get("fastBotDetection", False),
        })
    
    # Post-process sorting for device_type since it's derived
    if sort_by == "device_type":
        sessions_list.sort(key=lambda x: x["device_type"], reverse=(sort_order != "asc"))

    return jsonify({
        "sessions": sessions_list,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
    }), 200


@sessions_bp.route("/sessions/<fsid>", methods=["GET"])
@require_auth
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


@sessions_bp.route("/sessions/<fsid>", methods=["DELETE"])
@require_auth
@require_role("user", "admin")
def delete_session(fsid):
    """
    Delete a session and all related records.
    """
    from services.database import db
    sess = Session.query.filter_by(fsid=fsid).first()
    if not sess:
        return jsonify({"error": "session not found"}), 404

    # Explicitly delete children (lazy="dynamic" prevents ORM cascade)
    Fingerprint.query.filter_by(session_id=sess.id).delete()
    Heartbeat.query.filter_by(session_id=sess.id).delete()
    SessionURL.query.filter_by(session_id=sess.id).delete()
    BrowserSession.query.filter_by(session_id=sess.id).delete()
    RuleMatch.query.filter_by(session_id=sess.id).delete()

    db.session.delete(sess)
    db.session.commit()
    return jsonify({"deleted": fsid}), 200

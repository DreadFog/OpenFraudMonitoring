"""
Sessions endpoints - list and detail views
"""

import json
from flask import Blueprint, request, jsonify
from models import Session, Fingerprint, Heartbeat, BehavioralEvent
from models.behavioral_event import CopyEvent, PasteEvent, FormSubmitEvent, ButtonClickEvent, TYPED_EVENT_MODELS
from models.associations import SessionURL, BrowserSession
from models.rule import RuleMatch
from rules.engine import build_session_query
from services.auth import require_auth, require_role
from services.settings import get_global_setting, CLIPBOARD_CENSOR_KEY


def _censor_text(value):
    """Return only the first and last character, masking the middle."""
    s = str(value)
    if len(s) <= 2:
        return s
    return s[0] + "•" * (len(s) - 2) + s[-1]


def _censor_event(evt):
    """Censor sensitive captured content in a behavioral-event dict.

    Applies to copy/paste `text` (flat field in the new typed schema).
    Form-submit field values are not captured in the new schema (only names).
    """
    event_type = evt.get("event_type")
    if event_type in ("copy", "paste") and evt.get("text"):
        evt = {**evt, "text": _censor_text(evt["text"])}
    return evt


def _fetch_typed_events(session_id: int, limit: int = 2000) -> list[dict]:
    """Return all typed behavioral events for a session, sorted oldest-first.

    Queries all 4 typed tables, merges, sorts by timestamp, and applies the
    given limit (keeping the most recent *limit* events).
    """
    rows = []
    for Model in TYPED_EVENT_MODELS.values():
        rows.extend(Model.query.filter_by(session_id=session_id).all())
    rows.sort(key=lambda r: r.timestamp or 0, reverse=True)
    rows = rows[:limit]
    rows.reverse()  # present oldest-first in the timeline
    return [r.to_dict() for r in rows]

# Platforms that are unambiguously desktop/workstation
sessions_bp = Blueprint("sessions", __name__, url_prefix="/api")


@sessions_bp.route("/sessions", methods=["GET"])
@require_auth
def get_sessions():
    """
    Get paginated sessions with basic info.
    Accepts optional query params:
    - filters: JSON array of conditions
    - sort_by: 'last_seen', 'risk_score', 'first_seen', or 'client_ip' (default: 'last_seen')
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
        urls = [u.url for u in sess.urls.limit(3).all()]
        urls_count = sess.urls.count()
        heartbeats_count = sess.heartbeats.count()
        behavioral_events_count = sum(
            Model.query.filter_by(session_id=sess.id).count()
            for Model in TYPED_EVENT_MODELS.values()
        )
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
            "device_id": sess.device_id,
            "heartbeats": heartbeats_count,
            "behavioral_events": behavioral_events_count,
            "urls": urls,
            "user_agent": str(browser.get("userAgent", "unknown"))[:60],
            "platform": str(device.get("platform", "unknown")),
            "language": str(locale.get("languages", {}).get("language", "unknown")),
            "urls_count": urls_count,
            "session_ids": session_ids,
            "fast_bot_detection": last_fp.get("fastBotDetection", False),
        })

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
    behavioral_events_count = sum(
        Model.query.filter_by(session_id=sess.id).count()
        for Model in TYPED_EVENT_MODELS.values()
    )
    fingerprints_count = sess.fingerprints.count()

    last_fp_row = sess.fingerprints.order_by(Fingerprint.timestamp.desc()).first()
    latest_fingerprint = last_fp_row.data if last_fp_row else None

    # Fetch the most recent events, then present them oldest-first so the
    # session-detail timeline reads top (earliest) to bottom (latest).
    recent_heartbeats = sess.heartbeats.order_by(
        Heartbeat.timestamp.desc()
    ).limit(2000).all()
    recent_heartbeats.reverse()

    behavioral_events = _fetch_typed_events(sess.id, limit=2000)
    if bool(get_global_setting(CLIPBOARD_CENSOR_KEY)):
        behavioral_events = [_censor_event(e) for e in behavioral_events]

    return jsonify({
        "fsid": fsid,
        "client_ip": sess.client_ip,
        "risk_score": sess.risk_score,
        "flags": sess.flags or [],
        "first_seen": sess.first_seen,
        "last_seen": sess.last_seen,
        "device_id": sess.device_id,
        "urls": urls,
        "session_ids": session_ids,
        "heartbeats_count": heartbeats_count,
        "behavioral_events_count": behavioral_events_count,
        "fingerprints_count": fingerprints_count,
        "latest_fingerprint": latest_fingerprint,
        "heartbeats": [hb.to_summary() for hb in recent_heartbeats],
        "behavioral_events": behavioral_events,
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
    BehavioralEvent.query.filter_by(session_id=sess.id).delete()  # legacy table
    from models.behavioral_event import CopyEvent, PasteEvent, FormSubmitEvent, ButtonClickEvent
    CopyEvent.query.filter_by(session_id=sess.id).delete()
    PasteEvent.query.filter_by(session_id=sess.id).delete()
    FormSubmitEvent.query.filter_by(session_id=sess.id).delete()
    ButtonClickEvent.query.filter_by(session_id=sess.id).delete()
    SessionURL.query.filter_by(session_id=sess.id).delete()
    BrowserSession.query.filter_by(session_id=sess.id).delete()
    RuleMatch.query.filter_by(session_id=sess.id).delete()

    db.session.delete(sess)
    db.session.commit()
    return jsonify({"deleted": fsid}), 200

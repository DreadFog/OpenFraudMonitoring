"""
Behavioral Event endpoint — receives direct behavioral events (button clicks, form submits, copy/paste).

Expected payload:
  {
    "fsid": "<session_fingerprint_id>",
    "timestamp": 1234567890,
    "url": "https://...",
    "event_type": "button_click|form_submit|copy|paste",
    "data": { ... }  # event-specific data
  }
"""

import logging
from flask import Blueprint, request, jsonify
from services.database import db
from models import Session, TYPED_EVENT_MODELS
from models import AuthAttemptEvent
from services.event_queue import enqueue_event
from services.domains import add_session_domain, matching_form_config

logger = logging.getLogger(__name__)

behavioral_event_bp = Blueprint("behavioral_event", __name__, url_prefix="/api")

# Allowed event types (must match TYPED_EVENT_MODELS keys)
ALLOWED_EVENT_TYPES = set(TYPED_EVENT_MODELS.keys())


def _build_typed_event(Model, session_id, timestamp, url, data):
    """Construct a typed event model instance from the ingested payload dict."""
    kwargs = {"session_id": session_id, "timestamp": timestamp, "url": url}

    if Model.EVENT_TYPE == "copy":
        kwargs.update({
            "length": int(data.get("length") or 0),
            "text": data.get("text") or None,
            "source_tag": str(data.get("sourceTag") or "")[:64],
            "source_id": str(data.get("sourceId") or "")[:256],
            "source_name": str(data.get("sourceName") or "")[:256],
            "source_type": str(data.get("sourceType") or "")[:64],
            "form_action": str(data.get("formAction") or "")[:2048],
        })
    elif Model.EVENT_TYPE == "paste":
        kwargs.update({
            "length": int(data.get("length") or 0),
            "text": data.get("text") or None,
            "target_tag": str(data.get("targetTag") or "")[:64],
            "target_id": str(data.get("targetId") or "")[:256],
            "target_name": str(data.get("targetName") or "")[:256],
            "target_type": str(data.get("targetType") or "")[:64],
            "form_action": str(data.get("formAction") or "")[:2048],
        })
    elif Model.EVENT_TYPE == "form_submit":
        kwargs.update({
            "action": str(data.get("action") or "")[:2048],
            "method": str(data.get("method") or "")[:16],
            "field_names": data.get("fieldNames") or [],
        })
    elif Model.EVENT_TYPE == "button_click":
        kwargs.update({
            "x": int(data["x"]) if data.get("x") is not None else None,
            "y": int(data["y"]) if data.get("y") is not None else None,
            "tag": str(data.get("tag") or "")[:64],
            "text": str(data.get("text") or "")[:512],
        })

    return Model(**kwargs)


@behavioral_event_bp.route("/behavioral_event", methods=["POST"])
def behavioral_event():
    """
    Receive and store a behavioral event in the appropriate typed table.
    """
    payload = request.get_json() or {}

    fsid = payload.get("fsid")
    timestamp = payload.get("timestamp", 0)
    url = payload.get("url", "")
    event_type = payload.get("event_type", "")
    data = payload.get("data", {})

    # Validate event_type
    if event_type == "auth_attempt":
        return jsonify({"ok": False, "error": "auth_attempt events are generated server-side"}), 400
    if event_type not in ALLOWED_EVENT_TYPES:
        return jsonify({"ok": False, "error": f"Invalid event_type: {event_type}"}), 400

    # Find session by fsid, then IP fallback
    session_obj = None
    if fsid:
        session_obj = Session.query.filter_by(fsid=fsid).first()
    if not session_obj:
        forwarded = request.headers.get("X-Forwarded-For", "")
        client_ip = (forwarded.split(",")[0].strip() if forwarded else "") or request.remote_addr
        session_obj = Session.query.filter_by(client_ip=client_ip).order_by(
            Session.last_seen.desc()
        ).first()

    if not session_obj:
        return jsonify({"ok": False, "error": "session not found"}), 404

    # Dispatch to the appropriate typed model
    Model = TYPED_EVENT_MODELS[event_type]
    event_obj = _build_typed_event(Model, session_obj.id, timestamp, url, data)
    db.session.add(event_obj)
    add_session_domain(session_obj, url)
    if event_type == "form_submit":
        action = str(data.get("action") or "")[:2048]
        method = str(data.get("method") or "post")[:16]
        field_names = data.get("fieldNames") or []
        config = matching_form_config(request.host, action, method, field_names)
        if config:
            logger.info(
                "authentication attempt detected: fsid=%s host=%s config_id=%s action=%s method=%s submitted_field_count=%d",
                session_obj.fsid[:32], request.host, config.id, action,
                method.lower(), len(field_names),
            )
            db.session.add(AuthAttemptEvent(
                session_id=session_obj.id,
                domain_config_id=config.id,
                timestamp=timestamp,
                url=url,
                action=action,
                method=method.lower(),
                matched_field_names=field_names,
            ))
    session_obj.last_seen = timestamp
    db.session.commit()

    # Enqueue for rule evaluation (best-effort)
    enqueue_event(session_obj.id, "behavioral_event")

    logger.debug("behavioral_event: fsid=%s type=%s url=%s", fsid[:32] if fsid else "", event_type, url)

    return jsonify({"ok": True}), 200

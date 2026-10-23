"""
Devices endpoints — list and detail views for fuzzy-matched device clusters.

See services/device_matching.py for how sessions are linked to a Device.
"""

import json

from flask import Blueprint, request, jsonify
from sqlalchemy import func
from models import Session
from models.device import Device
from services.auth import require_auth
from services.device_filters import build_device_query, get_device_schema, suggest_device_values
from services.database import db

devices_bp = Blueprint("devices", __name__, url_prefix="/api")


def _device_summary(device, counts):
    return {
        "id": device.id,
        "platform": device.platform,
        "screen_resolution": f"{int(device.screen_width)}x{int(device.screen_height)}" if device.screen_width else "unknown",
        "webgl_renderer": device.webgl_renderer,
        "device_type": device.device_type,
        "is_mobile": device.is_mobile,
        "confidence": device.confidence,
        "cookie_id": device.cookie_id,
        "sessions_count": counts[0],
        "distinct_fsids": counts[1],
        "distinct_ips": counts[2],
        "first_seen": device.first_seen,
        "last_seen": device.last_seen,
    }


@devices_bp.route("/devices", methods=["GET"])
@require_auth
def get_devices():
    """Get paginated devices, most recently active first."""
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

    try:
        filters = json.loads(request.args.get("filters", "[]"))
    except (json.JSONDecodeError, TypeError):
        filters = []
    if not isinstance(filters, list):
        filters = []

    query = build_device_query(filters, logic=request.args.get("logic", "AND")).order_by(Device.last_seen.desc())
    total = query.count()
    pages = max(1, -(-total // per_page))  # ceil division
    page = min(page, pages)
    offset = (page - 1) * per_page

    devices = query.offset(offset).limit(per_page).all()
    counts = {
        device_id: (sessions, fsids, ips)
        for device_id, sessions, fsids, ips in (
            db.session.query(
                Session.device_id, func.count(Session.id),
                func.count(func.distinct(Session.fsid)),
                func.count(func.distinct(func.nullif(Session.client_ip, ""))),
            )
            .filter(Session.device_id.in_([device.id for device in devices]))
            .group_by(Session.device_id).all()
        )
    } if devices else {}

    return jsonify({
        "devices": [_device_summary(d, counts.get(d.id, (0, 0, 0))) for d in devices],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
    }), 200


@devices_bp.route("/devices/schema", methods=["GET"])
@require_auth
def get_devices_schema():
    """Filterable device fields, generated from the Device model plus linked-session aggregates."""
    return jsonify(get_device_schema()), 200


@devices_bp.route("/devices/suggest", methods=["GET"])
@require_auth
def suggest_devices():
    return jsonify(suggest_device_values(request.args.get("field", ""), request.args.get("q", ""))), 200


@devices_bp.route("/devices/<int:device_id>", methods=["GET"])
@require_auth
def get_device_detail(device_id):
    """Get canonical fields and a bounded page of linked sessions."""
    device = Device.query.get(device_id)
    if not device:
        return jsonify({"error": "device not found"}), 404

    try:
        page = max(1, int(request.args.get("page", "1")))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = int(request.args.get("per_page", "25"))
    except (ValueError, TypeError):
        per_page = 25
    if per_page not in (10, 25, 50, 100):
        per_page = 25
    query = Session.query.filter_by(device_id=device.id)
    total = query.count()
    pages = max(1, -(-total // per_page))
    page = min(page, pages)
    sessions = (
        query.order_by(Session.last_seen.desc(), Session.id.desc())
        .offset((page - 1) * per_page).limit(per_page).all()
    )

    return jsonify({
        "id": device.id,
        "cookie_id": device.cookie_id,
        "confidence": device.confidence,
        "platform": device.platform,
        "device_type": device.device_type,
        "is_mobile": device.is_mobile,
        "screen_width": device.screen_width,
        "screen_height": device.screen_height,
        "pixel_depth": device.pixel_depth,
        "color_depth": device.color_depth,
        "cpu_count": device.cpu_count,
        "memory": device.memory,
        "match_profile": device.match_profile or {},
        "speakers": device.speakers,
        "microphones": device.microphones,
        "webcams": device.webcams,
        "webgl_vendor": device.webgl_vendor,
        "webgl_renderer": device.webgl_renderer,
        "hev_architecture": device.hev_architecture,
        "hev_bitness": device.hev_bitness,
        "hev_model": device.hev_model,
        "hev_platform": device.hev_platform,
        "hev_platform_version": device.hev_platform_version,
        "timezone": device.timezone,
        "language": device.language,
        "recent_ips": device.recent_ips or [],
        "first_seen": device.first_seen,
        "last_seen": device.last_seen,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "sessions": [
            {
                "id": s.id,
                "visit_id": s.visit_id,
                "fsid": s.fsid,
                "risk_score": s.risk_score,
                "client_ip": s.client_ip,
                "first_seen": s.first_seen,
                "last_seen": s.last_seen,
            }
            for s in sessions
        ],
    }), 200

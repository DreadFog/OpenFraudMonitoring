"""
Overview endpoints for the landing page: triage summary, setup status, quick search.
"""

import time

from flask import Blueprint, jsonify, request
from sqlalchemy import func, or_

from models import AllowedOrigin, DomainConfig, Rule, RuleMatch, Session
from models.device import Device
from routes.connectors import _connector_info, _list_connectors
from services.auth import require_auth
from services.database import db
from services.stix_filters import TYPE_TO_MODEL

overview_bp = Blueprint("overview", __name__, url_prefix="/api/overview")

DAY_MS = 24 * 60 * 60 * 1000
HIGH_RISK = 60
# Same heuristic as /api/stats: flags named after automation detections.
_BOT_KEYWORDS = ("Webdriver", "Selenium", "CDP", "Playwright", "Bot")
_SEARCH_STIX_TYPES = ("ipv4-addr", "ipv6-addr", "user-agent", "autonomous-system")


def _is_bot(flags):
    return any(any(kw in str(f) for kw in _BOT_KEYWORDS) for f in flags or [])


def _window_counts(start, end):
    active = Session.query.filter(Session.last_seen >= start, Session.last_seen < end)
    flags = [row[0] for row in active.with_entities(Session.flags).all()]
    return {
        "sessions": len(flags),
        "high_risk": active.filter(Session.risk_score >= HIGH_RISK).count(),
        "bots": sum(1 for f in flags if _is_bot(f)),
        "new_devices": Device.query.filter(Device.first_seen >= start, Device.first_seen < end).count(),
    }


def _rule_activity():
    hours_ago = func.floor(func.extract("epoch", func.now() - RuleMatch.matched_at) / 3600)
    rows = (
        db.session.query(RuleMatch.rule_id, hours_ago.label("h"), func.count(RuleMatch.id))
        .filter(RuleMatch.matched_at >= func.now() - func.make_interval(0, 0, 0, 2))
        .group_by(RuleMatch.rule_id, "h")
        .all()
    )
    by_rule = {}
    for rule_id, h, count in rows:
        entry = by_rule.setdefault(rule_id, {"current": 0, "previous": 0, "hourly": [0] * 24})
        h = int(h)
        if h < 24:
            entry["current"] += count
            entry["hourly"][23 - h] += count
        else:
            entry["previous"] += count

    names = dict(Rule.query.with_entities(Rule.id, Rule.name).filter(Rule.id.in_(by_rule)).all()) if by_rule else {}
    result = [
        {
            "rule_id": rule_id,
            "name": names.get(rule_id, f"Rule #{rule_id}"),
            **entry,
            "spike": entry["current"] >= 5 and entry["current"] >= 2 * entry["previous"],
        }
        for rule_id, entry in by_rule.items()
        if entry["current"] > 0
    ]
    result.sort(key=lambda r: r["current"], reverse=True)
    return result[:8]


def _setup_status():
    connectors = [_connector_info(name) for name in _list_connectors()]
    return {
        "has_sessions": db.session.query(Session.query.exists()).scalar(),
        "active_origins": AllowedOrigin.query.filter_by(active=True).count(),
        "active_domains": DomainConfig.query.filter_by(active=True).count(),
        "connectors": len(connectors),
        "healthy_connectors": sum(1 for c in connectors if c["healthy"]),
        "enabled_rules": Rule.query.filter_by(enabled=True).count(),
    }


@overview_bp.route("", methods=["GET"])
@require_auth
def overview():
    now = time.time() * 1000
    review = (
        Session.query
        .filter(Session.last_seen >= now - DAY_MS, Session.risk_score >= HIGH_RISK)
        .order_by(Session.risk_score.desc(), Session.last_seen.desc())
        .limit(8)
        .all()
    )
    return jsonify({
        "current": _window_counts(now - DAY_MS, now + 1),
        "previous": _window_counts(now - 2 * DAY_MS, now - DAY_MS),
        "review": [
            {
                "fsid": s.fsid,
                "risk_score": s.risk_score,
                "flags": s.flags or [],
                "client_ip": s.client_ip,
                "last_seen": s.last_seen,
                "device_id": s.device_id,
            }
            for s in review
        ],
        "rules": _rule_activity(),
        "setup": _setup_status(),
    }), 200


@overview_bp.route("/search", methods=["GET"])
@require_auth
def search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"sessions": [], "devices": [], "entities": []}), 200

    sessions = (
        Session.query
        .filter(or_(Session.fsid.ilike(f"{q}%"), Session.client_ip.ilike(f"{q}%")))
        .order_by(Session.last_seen.desc())
        .limit(5)
        .all()
    )

    device_conds = [Device.cookie_id.ilike(f"{q}%")]
    if q.lstrip("#").isdigit():
        device_conds.append(Device.id == int(q.lstrip("#")))
    devices = Device.query.filter(or_(*device_conds)).order_by(Device.last_seen.desc()).limit(5).all()

    entities = []
    for stix_type in _SEARCH_STIX_TYPES:
        Model = TYPE_TO_MODEL[stix_type]
        for ent in Model.query.filter(Model.value.ilike(f"%{q}%")).limit(3).all():
            entities.append({"type": stix_type, "value": ent.value, "name": (ent.raw or {}).get("name")})

    return jsonify({
        "sessions": [
            {"fsid": s.fsid, "client_ip": s.client_ip, "risk_score": s.risk_score, "last_seen": s.last_seen}
            for s in sessions
        ],
        "devices": [{"id": d.id, "platform": d.platform, "device_type": d.device_type} for d in devices],
        "entities": entities,
    }), 200

"""
Dashboard endpoints — CRUD for saved dashboards and widget data aggregation.
"""

from datetime import datetime, timezone

from flask import Blueprint, request, jsonify
from sqlalchemy import func as sa_func
from services.database import db
from models.dashboard import Dashboard
from models import Session, Fingerprint
from models.rule import Rule, RuleMatch
from rules.engine import build_session_query
from services.schema import get_field_meta
from services.auth import require_auth, require_role
from filters import get_custom_aggregate

dashboards_bp = Blueprint("dashboards", __name__, url_prefix="/api")


# ── Dashboard CRUD ──────────────────────────────────────────────────────────


@dashboards_bp.route("/dashboards", methods=["GET"])
@require_auth
@require_role("user", "admin")
def list_dashboards():
    dashboards = Dashboard.query.order_by(Dashboard.name).all()
    return jsonify([d.to_dict() for d in dashboards]), 200


@dashboards_bp.route("/dashboards", methods=["POST"])
@require_auth
@require_role("user", "admin")
def create_dashboard():
    body = request.get_json()
    name = (body.get("name") or "").strip()
    widgets = body.get("widgets", [])
    if not name:
        return jsonify({"error": "name is required"}), 400
    if Dashboard.query.filter_by(name=name).first():
        return jsonify({"error": "dashboard name already exists"}), 409
    dashboard = Dashboard(name=name, widgets=widgets)
    db.session.add(dashboard)
    db.session.commit()
    return jsonify(dashboard.to_dict()), 201


@dashboards_bp.route("/dashboards/<int:dashboard_id>", methods=["PUT"])
@require_auth
@require_role("user", "admin")
def update_dashboard(dashboard_id):
    dashboard = db.session.get(Dashboard, dashboard_id)
    if not dashboard:
        return jsonify({"error": "not found"}), 404
    body = request.get_json()
    if "name" in body:
        new_name = (body["name"] or "").strip()
        if not new_name:
            return jsonify({"error": "name cannot be empty"}), 400
        dashboard.name = new_name
    if "widgets" in body:
        dashboard.widgets = body["widgets"]
    db.session.commit()
    return jsonify(dashboard.to_dict()), 200


@dashboards_bp.route("/dashboards/<int:dashboard_id>", methods=["DELETE"])
@require_auth
@require_role("user", "admin")
def delete_dashboard(dashboard_id):
    dashboard = db.session.get(Dashboard, dashboard_id)
    if not dashboard:
        return jsonify({"error": "not found"}), 404
    db.session.delete(dashboard)
    db.session.commit()
    return jsonify({"deleted": dashboard_id}), 200


# ── Widget data aggregation ─────────────────────────────────────────────────


@dashboards_bp.route("/widget-data", methods=["POST"])
@require_auth
@require_role("user", "admin")
def widget_data():
    """
    Compute aggregated data for a single widget.

    Body JSON:
        type    – "stat" | "pie" | "histogram" | "weighted_list"
        field   – schema field name (required for non-stat types)
        filters – array of {field, op, value} filter conditions
        limit   – max groups to return (default 10)
    """
    body = request.get_json() or {}
    widget_type = body.get("type", "stat")
    field = body.get("field")
    filters = body.get("filters", [])
    limit = min(int(body.get("limit", 10)), 200)

    # Map widgets always group by ip_country
    if widget_type == "map":
        field = "ip_country"

    # Build filtered session query
    query = build_session_query(filters)

    # Stat widgets just return a count
    if widget_type == "stat":
        return jsonify({"count": query.count()}), 200

    if widget_type == "timeline":
        try:
            start_ms, end_ms = int(body["from"]), int(body["to"])
            start = datetime.fromtimestamp(start_ms / 1000, timezone.utc).replace(tzinfo=None)
            end = datetime.fromtimestamp(end_ms / 1000, timezone.utc).replace(tzinfo=None)
        except (KeyError, TypeError, ValueError, OverflowError):
            return jsonify({"error": "valid from and to timestamps are required"}), 400
        if start >= end:
            return jsonify({"error": "from must be earlier than to"}), 400

        span = end_ms - start_ms
        requested_unit = body.get("granularity")
        unit = requested_unit if requested_unit in ("minute", "hour", "day") else (
            "minute" if span < 3600000 else "hour" if span <= 86400000 else "day"
        )
        bucket = sa_func.date_trunc(unit, RuleMatch.matched_at)
        rows = (
            db.session.query(bucket, Rule.name, sa_func.count(RuleMatch.id))
            .join(Rule, Rule.id == RuleMatch.rule_id)
            .filter(
                RuleMatch.session_id.in_(query.with_entities(Session.id)),
                RuleMatch.matched_at >= start,
                RuleMatch.matched_at <= end,
            )
            .group_by(bucket, Rule.name)
            .order_by(bucket, Rule.name)
            .all()
        )
        return jsonify({
            "unit": unit,
            "groups": [
                {"bucket": bucket_start.isoformat() + "Z", "value": name, "count": count}
                for bucket_start, name, count in rows
            ],
        }), 200

    # All other types require a field to group by
    if not field:
        return jsonify({"error": "field is required for this widget type"}), 400

    meta = get_field_meta(field)
    if not meta:
        return jsonify({"error": f"unknown field: {field}"}), 400

    # Build the GROUP BY query
    session_ids = query.with_entities(Session.id)

    # Custom filters have their own aggregate logic
    if meta["model"] == "__custom__":
        id_list = [r[0] for r in session_ids.all()]
        groups = get_custom_aggregate(field, id_list, limit)
        if groups is None:
            return jsonify({"error": f"field '{field}' does not support aggregation"}), 400
        return jsonify({"groups": groups}), 200

    if meta["model"] == "Session":
        column = getattr(Session, meta["column"])
        results = (
            db.session.query(column, sa_func.count())
            .filter(Session.id.in_(session_ids))
            .group_by(column)
            .order_by(sa_func.count().desc())
            .limit(limit)
            .all()
        )
    else:
        column = getattr(Fingerprint, meta["column"])
        results = (
            db.session.query(
                column, sa_func.count(sa_func.distinct(Fingerprint.session_id))
            )
            .filter(Fingerprint.session_id.in_(session_ids))
            .group_by(column)
            .order_by(sa_func.count(sa_func.distinct(Fingerprint.session_id)).desc())
            .limit(limit)
            .all()
        )

    groups = [
        {
            "value": str(row[0]) if row[0] is not None else "N/A",
            "count": row[1],
        }
        for row in results
    ]

    return jsonify({"groups": groups}), 200

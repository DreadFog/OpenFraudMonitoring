"""
Dashboard endpoints — CRUD for saved dashboards and widget data aggregation.
"""

from flask import Blueprint, request, jsonify
from sqlalchemy import func as sa_func
from services.database import db
from models.dashboard import Dashboard
from models import Session, Fingerprint
from rules.engine import build_session_query
from services.schema import get_field_meta

dashboards_bp = Blueprint("dashboards", __name__, url_prefix="/api")


# ── Dashboard CRUD ──────────────────────────────────────────────────────────


@dashboards_bp.route("/dashboards", methods=["GET"])
def list_dashboards():
    dashboards = Dashboard.query.order_by(Dashboard.name).all()
    return jsonify([d.to_dict() for d in dashboards]), 200


@dashboards_bp.route("/dashboards", methods=["POST"])
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
def delete_dashboard(dashboard_id):
    dashboard = db.session.get(Dashboard, dashboard_id)
    if not dashboard:
        return jsonify({"error": "not found"}), 404
    db.session.delete(dashboard)
    db.session.commit()
    return jsonify({"deleted": dashboard_id}), 200


# ── Widget data aggregation ─────────────────────────────────────────────────


@dashboards_bp.route("/widget-data", methods=["POST"])
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

    # Build filtered session query
    query = build_session_query(filters)

    # Stat widgets just return a count
    if widget_type == "stat":
        return jsonify({"count": query.count()}), 200

    # All other types require a field to group by
    if not field:
        return jsonify({"error": "field is required for this widget type"}), 400

    meta = get_field_meta(field)
    if not meta:
        return jsonify({"error": f"unknown field: {field}"}), 400

    # Build the GROUP BY query
    session_ids = query.with_entities(Session.id)

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

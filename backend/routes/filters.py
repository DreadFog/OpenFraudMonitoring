"""
Schema and suggestion endpoints for frontend filtering.
"""

from flask import Blueprint, request, jsonify
from services.database import db
from services.schema import get_schema, get_field_meta
from services.auth import require_auth

filters_bp = Blueprint("filters", __name__, url_prefix="/api")


@filters_bp.route("/schema", methods=["GET"])
@require_auth
def schema():
    """Return the list of filterable fields with their types and operators."""
    return jsonify(get_schema()), 200


@filters_bp.route("/suggest", methods=["GET"])
@require_auth
def suggest():
    """
    Return up to 20 distinct values for a given field, optionally filtered
    by a search term.  Used by the frontend filter builder for autocomplete.

    Query params:
        field – schema field name (e.g. "client_ip")
        q     – optional search substring
    """
    field_name = request.args.get("field", "")
    q = request.args.get("q", "")

    meta = get_field_meta(field_name)
    if not meta:
        return jsonify([]), 200

    # Boolean fields → static options
    if meta["type"] == "boolean":
        options = ["true", "false"]
        if q:
            options = [o for o in options if q.lower() in o]
        return jsonify(options), 200

    # Number fields → no autocomplete
    if meta["type"] == "number":
        return jsonify([]), 200

    # String fields → query distinct values from the database
    from models import Session, Fingerprint

    model_map = {"Session": Session, "Fingerprint": Fingerprint}
    model = model_map[meta["model"]]
    column = getattr(model, meta["column"])

    query = db.session.query(column.distinct())
    query = query.filter(column != None, column != "")  # noqa: E711
    if q:
        query = query.filter(column.ilike(f"%{q}%"))
    results = query.limit(20).all()

    return jsonify([row[0] for row in results]), 200

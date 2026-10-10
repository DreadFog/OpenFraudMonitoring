"""Authenticated CSV/TAXII feed management and configurable CSV downloads."""

from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, request

from models import TaxiiFeed
from services.auth import require_auth, require_role
from services.database import db
from services.stix_filters import TYPE_TO_MODEL, apply_filters
from services.stix_objects import export_field_names
from services.csv_feeds import validate_feed_options, matching_rows, render_csv, refresh_csv_feed, update_csv_batch


taxii_feeds_bp = Blueprint("taxii_feeds", __name__, url_prefix="/api/taxii-feeds")
csv_feeds_bp = Blueprint("csv_feeds", __name__, url_prefix="/api/csv")

_ALLOWED_TYPES = set(TYPE_TO_MODEL.keys()) | {"relationship"}


def _normalize_object_types(payload_value) -> list[str]:
    if payload_value in (None, ""):
        return sorted(_ALLOWED_TYPES)

    if not isinstance(payload_value, list):
        raise ValueError("object_types must be an array")

    types = []
    seen = set()
    for item in payload_value:
        t = str(item or "").strip().lower()
        if not t:
            continue
        if t not in _ALLOWED_TYPES:
            raise ValueError(f"unsupported object type '{t}'")
        if t not in seen:
            seen.add(t)
            types.append(t)

    if not types:
        raise ValueError("object_types must contain at least one type")

    return types


def _with_urls(feed: TaxiiFeed) -> dict:
    data = feed.to_dict()
    root = request.url_root.rstrip("/")
    if feed.export_format == "csv":
        data["objects_url"] = f"{root}/api/csv/{feed.uuid}/"
    else:
        data["collection_url"] = f"{root}/taxii2/default/collections/{feed.uuid}/"
        data["objects_url"] = f"{root}/taxii2/default/collections/{feed.uuid}/objects/"
    return data


def _parse_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)

    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "on"):
        return True
    if text in ("false", "0", "no", "off"):
        return False
    return default


@taxii_feeds_bp.route("/export-fields", methods=["GET"])
@require_auth
def export_fields():
    stix_type = request.args.get("type", "")
    if stix_type not in _ALLOWED_TYPES:
        return jsonify({"error": "unsupported object type"}), 400
    return jsonify({"fields": export_field_names(stix_type)})


@taxii_feeds_bp.route("/<collection_id>/csv", methods=["GET"])
@csv_feeds_bp.route("/<collection_id>/", methods=["GET"])
def download_csv(collection_id):
    from routes.taxii import _resolve_taxii_user, _AUTH_CHALLENGE
    feed = TaxiiFeed.query.filter_by(uuid=collection_id, is_active=True, export_format="csv").first()
    if feed is None:
        return jsonify({"error": "feed not found"}), 404
    if not feed.is_public and _resolve_taxii_user() is None:
        return jsonify({"error": "unauthorized"}), 401, {"WWW-Authenticate": _AUTH_CHALLENGE}
    try:
        if feed.auto_update:
            feed = refresh_csv_feed(feed.id)
            content = feed.csv_content or ""
        else:
            content = render_csv(matching_rows(feed), feed.export_fields, feed.include_headers, feed.csv_delimiter)
            db.session.commit()
    except ValueError as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400
    response = Response(content, content_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f'attachment; filename="feed-{feed.uuid}.csv"'
    response.headers["Cache-Control"] = "no-store"
    if feed.last_generated_at:
        response.headers["X-OFM-Generated-At"] = feed.last_generated_at.isoformat() + "Z"
    return response


def _validate_filters(types, filters, logic):
    if not isinstance(filters, list):
        raise ValueError("filters must be an array")
    if not filters:
        return
    from models import StixRelationship
    errors = []
    for stix_type in types:
        model = StixRelationship if stix_type == "relationship" else TYPE_TO_MODEL[stix_type]
        _, error = apply_filters(model.query, stix_type, filters, logic)
        if error is None:
            return
        errors.append(error)
    raise ValueError(errors[0])


@taxii_feeds_bp.route("", methods=["GET"])
@require_auth
def list_taxii_feeds():
    rows = TaxiiFeed.query.order_by(TaxiiFeed.updated_at.desc(), TaxiiFeed.id.desc()).all()
    return jsonify({"feeds": [_with_urls(row) for row in rows]}), 200


@taxii_feeds_bp.route("/<int:feed_id>", methods=["GET"])
@require_auth
def get_taxii_feed(feed_id: int):
    feed = TaxiiFeed.query.get(feed_id)
    if feed is None:
        return jsonify({"error": "feed not found"}), 404
    return jsonify(_with_urls(feed)), 200


@taxii_feeds_bp.route("", methods=["POST"])
@require_auth
@require_role("admin")
def create_taxii_feed():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "body must be a JSON object"}), 400

    name = str(body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    try:
        object_types = _normalize_object_types(body.get("object_types"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    filters = body.get("filters")
    if filters is None:
        filters = []
    if not isinstance(filters, list):
        return jsonify({"error": "filters must be an array"}), 400

    try:
        options = validate_feed_options({**body, "object_types": object_types})
        _validate_filters(object_types, filters, options["filter_logic"])
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    feed = TaxiiFeed(
        name=name,
        description=(body.get("description") or "").strip() or None,
        is_active=_parse_bool(body.get("is_active"), default=True),
        object_types=object_types,
        filters=filters,
        owner_user_id=g.current_user.id,
        **options,
    )
    db.session.add(feed)
    db.session.flush()
    if feed.export_format == "csv" and feed.auto_update:
        update_csv_batch(feed)
    db.session.commit()

    return jsonify(_with_urls(feed)), 201


@taxii_feeds_bp.route("/<int:feed_id>", methods=["PATCH"])
@require_auth
@require_role("admin")
def update_taxii_feed(feed_id: int):
    feed = TaxiiFeed.query.filter_by(id=feed_id).with_for_update().first()
    if feed is None:
        return jsonify({"error": "feed not found"}), 404

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "body must be a JSON object"}), 400

    try:
        types = _normalize_object_types(body.get("object_types", feed.object_types))
        options = validate_feed_options({**body, "object_types": types}, feed)
        _validate_filters(types, body.get("filters", feed.filters), options["filter_logic"])
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    reset_batch = any(key in body and body[key] != getattr(feed, key) for key in (
        "object_types", "filters", "filter_logic", "export_format", "export_fields", "include_headers", "csv_delimiter", "auto_update",
    ))

    if "name" in body:
        name = str(body.get("name") or "").strip()
        if not name:
            return jsonify({"error": "name cannot be empty"}), 400
        feed.name = name

    if "description" in body:
        feed.description = (body.get("description") or "").strip() or None

    if "is_active" in body:
        feed.is_active = _parse_bool(body.get("is_active"), default=feed.is_active)

    if "object_types" in body:
        try:
            feed.object_types = _normalize_object_types(body.get("object_types"))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    if "filters" in body:
        filters = body.get("filters")
        if not isinstance(filters, list):
            return jsonify({"error": "filters must be an array"}), 400
        feed.filters = filters

    for key, value in options.items():
        setattr(feed, key, value)
    if reset_batch:
        feed.matching_ids = []
        feed.csv_content = None
        feed.last_generated_at = None
    if feed.export_format == "csv" and feed.auto_update:
        update_csv_batch(feed)
    db.session.commit()
    return jsonify(_with_urls(feed)), 200


@taxii_feeds_bp.route("/<int:feed_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def delete_taxii_feed(feed_id: int):
    feed = TaxiiFeed.query.get(feed_id)
    if feed is None:
        return jsonify({"error": "feed not found"}), 404

    db.session.delete(feed)
    db.session.commit()
    return jsonify({"ok": True}), 200

"""Authenticated TAXII feed management endpoints."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from models import TaxiiFeed
from services.auth import require_auth, require_role
from services.database import db
from services.stix_filters import TYPE_TO_MODEL


taxii_feeds_bp = Blueprint("taxii_feeds", __name__, url_prefix="/api/taxii-feeds")

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

    feed = TaxiiFeed(
        name=name,
        description=(body.get("description") or "").strip() or None,
        is_active=_parse_bool(body.get("is_active"), default=True),
        object_types=object_types,
        filters=filters,
        owner_user_id=g.current_user.id,
    )
    db.session.add(feed)
    db.session.commit()

    return jsonify(_with_urls(feed)), 201


@taxii_feeds_bp.route("/<int:feed_id>", methods=["PATCH"])
@require_auth
@require_role("admin")
def update_taxii_feed(feed_id: int):
    feed = TaxiiFeed.query.get(feed_id)
    if feed is None:
        return jsonify({"error": "feed not found"}), 404

    body = request.get_json(silent=True) or {}

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

"""TAXII 2.1 read-only server endpoints for exporting STIX intelligence."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from functools import wraps
from typing import Any

from flask import Blueprint, g, jsonify, request

from models import StixRelationship, TaxiiFeed
from models.user import ApiToken, User
from services.auth import decode_jwt, hash_api_token
from services.database import db
from services.stix_filters import TYPE_TO_MODEL


taxii_bp = Blueprint("taxii", __name__, url_prefix="/taxii2")

_API_ROOT_SEGMENT = "default"
_COLLECTION_TITLE = "OpenFraudMonitoring Intelligence"


def _resolve_taxii_user():
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):].strip()
    else:
        token = (request.args.get("access_token") or "").strip()

    if not token:
        return None

    user = None

    token_hash = hash_api_token(token)
    api_token = ApiToken.query.filter_by(token_hash=token_hash, is_active=True).first()
    if api_token is not None:
        if api_token.expires_at and api_token.expires_at < datetime.utcnow():
            return None
        user = User.query.get(api_token.user_id)
        api_token.last_used_at = datetime.utcnow()
        db.session.commit()
    else:
        payload = decode_jwt(token)
        if payload is not None:
            user = User.query.get(payload.get("sub"))

    if user is None or not user.is_active:
        return None

    return user


def require_taxii_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _resolve_taxii_user()
        if user is None:
            return jsonify({"error": "unauthorized"}), 401
        g.current_user = user
        return fn(*args, **kwargs)

    return wrapper


def _external_base() -> str:
    # Drop trailing slash so URL assembly is predictable.
    return request.url_root.rstrip("/")


def _api_root_url() -> str:
    return f"{_external_base()}/taxii2/{_API_ROOT_SEGMENT}/"


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _encode_cursor(created_at: datetime, stix_id: str) -> str:
    payload = {"ts": created_at.isoformat(), "sid": stix_id}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str | None) -> tuple[datetime | None, str | None]:
    if not cursor:
        return None, None
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        payload = json.loads(decoded)
        ts = _parse_iso_datetime(payload.get("ts"))
        sid = str(payload.get("sid") or "")
        if ts is None or not sid:
            return None, None
        return ts, sid
    except Exception:
        return None, None


def _iter_rows_for_type(stix_type: str, limit: int, added_after: datetime | None, cursor_ts: datetime | None, cursor_sid: str | None) -> list[Any]:
    if stix_type == "relationship":
        model = StixRelationship
    else:
        model = TYPE_TO_MODEL.get(stix_type)

    if model is None:
        return []

    q = model.query
    if added_after is not None:
        q = q.filter(model.created_at_platform > added_after)

    if cursor_ts is not None and cursor_sid is not None:
        q = q.filter(
            (model.created_at_platform > cursor_ts)
            | ((model.created_at_platform == cursor_ts) & (model.stix_id > cursor_sid))
        )

    return (
        q.order_by(model.created_at_platform.asc(), model.stix_id.asc())
        .limit(limit + 1)
        .all()
    )


def _collect_objects(limit: int, added_after: datetime | None, cursor_ts: datetime | None, cursor_sid: str | None, type_filter: set[str] | None) -> tuple[list[dict], bool, str | None]:
    types = list(TYPE_TO_MODEL.keys()) + ["relationship"]
    if type_filter:
        types = [t for t in types if t in type_filter]

    rows = []
    saw_extra = False

    for stix_type in types:
        fetched = _iter_rows_for_type(stix_type, limit, added_after, cursor_ts, cursor_sid)
        if len(fetched) > limit:
            saw_extra = True
            fetched = fetched[:limit]

        for row in fetched:
            rows.append((row.created_at_platform, row.stix_id, row.raw or {}))

    rows.sort(key=lambda item: (item[0], item[1]))
    has_more = saw_extra or len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_more and rows:
        last_ts, last_sid, _ = rows[-1]
        next_cursor = _encode_cursor(last_ts, last_sid)

    objects = [raw for _, _, raw in rows if isinstance(raw, dict)]
    return objects, has_more, next_cursor


def _active_feed_by_uuid(collection_id: str) -> TaxiiFeed | None:
    return TaxiiFeed.query.filter_by(uuid=collection_id, is_active=True).first()


@taxii_bp.route("/", methods=["GET"])
def discovery():
    api_root = _api_root_url()
    return jsonify(
        {
            "title": "OpenFraudMonitoring TAXII",
            "description": "Read-only TAXII 2.1 API for OFM intelligence.",
            "default": api_root,
            "api_roots": [api_root],
        }
    ), 200


@taxii_bp.route(f"/{_API_ROOT_SEGMENT}/", methods=["GET"])
@require_taxii_auth
def api_root():
    base = _api_root_url()
    return jsonify(
        {
            "title": "OFM TAXII API Root",
            "description": "Read-only STIX object collections.",
            "versions": ["taxii-2.1"],
            "max_content_length": 10485760,
            "collections": f"{base}collections/",
        }
    ), 200


@taxii_bp.route(f"/{_API_ROOT_SEGMENT}/collections/", methods=["GET"])
@require_taxii_auth
def collections():
    base = _api_root_url()
    feeds = TaxiiFeed.query.filter_by(is_active=True).order_by(TaxiiFeed.updated_at.desc(), TaxiiFeed.id.desc()).all()
    return jsonify(
        {
            "collections": [
                {
                    "id": feed.uuid,
                    "title": feed.name or _COLLECTION_TITLE,
                    "description": feed.description or "Configured STIX export from OFM intelligence store.",
                    "can_read": True,
                    "can_write": False,
                    "media_types": ["application/stix+json;version=2.1"],
                    "objects": f"{base}collections/{feed.uuid}/objects/",
                }
                for feed in feeds
            ]
        }
    ), 200


@taxii_bp.route(f"/{_API_ROOT_SEGMENT}/collections/<collection_id>/", methods=["GET"])
@require_taxii_auth
def collection_detail(collection_id: str):
    feed = _active_feed_by_uuid(collection_id)
    if feed is None:
        return jsonify({"title": "Not Found", "description": "Unknown TAXII collection."}), 404

    base = _api_root_url()
    return jsonify(
        {
            "id": feed.uuid,
            "title": feed.name or _COLLECTION_TITLE,
            "description": feed.description or "Configured STIX export from OFM intelligence store.",
            "can_read": True,
            "can_write": False,
            "media_types": ["application/stix+json;version=2.1"],
            "objects": f"{base}collections/{feed.uuid}/objects/",
        }
    ), 200


@taxii_bp.route(f"/{_API_ROOT_SEGMENT}/collections/<collection_id>/objects/", methods=["GET"])
@require_taxii_auth
def collection_objects(collection_id: str):
    feed = _active_feed_by_uuid(collection_id)
    if feed is None:
        return jsonify({"title": "Not Found", "description": "Unknown TAXII collection."}), 404

    try:
        limit = int(request.args.get("limit", "100"))
    except (ValueError, TypeError):
        return jsonify({"title": "Invalid Parameter", "description": "limit must be an integer"}), 400

    limit = max(1, min(limit, 500))

    added_after = _parse_iso_datetime(request.args.get("added_after"))
    if request.args.get("added_after") and added_after is None:
        return jsonify({"title": "Invalid Parameter", "description": "added_after must be ISO-8601"}), 400

    cursor = request.args.get("next")
    cursor_ts, cursor_sid = _decode_cursor(cursor)
    if cursor and (cursor_ts is None or not cursor_sid):
        return jsonify({"title": "Invalid Parameter", "description": "next cursor is invalid"}), 400

    type_param = request.args.get("match[type]") or request.args.get("type")
    feed_types = {str(t).strip().lower() for t in (feed.object_types or []) if str(t).strip()}
    if not feed_types:
        feed_types = set(TYPE_TO_MODEL.keys()) | {"relationship"}

    type_filter = set(feed_types)
    if type_param:
        requested = {t.strip().lower() for t in str(type_param).split(",") if t.strip()}
        type_filter = feed_types.intersection(requested)

    objects, has_more, next_cursor = _collect_objects(
        limit=limit,
        added_after=added_after,
        cursor_ts=cursor_ts,
        cursor_sid=cursor_sid,
        type_filter=type_filter,
    )

    response = {
        "objects": objects,
        "more": has_more,
    }
    if has_more and next_cursor:
        response["next"] = next_cursor

    return jsonify(response), 200

"""Read-only TAXII 2.1 server (OASIS TAXII Version 2.1 OS) exporting STIX 2.1 objects.

Every collection maps to an active ``TaxiiFeed``; its ``object_types`` and
``filters`` scope the objects it exposes. Only the canonical STIX JSON stored
in ``raw`` is served. OFM keeps one version per object, so ``match[version]``
keywords (first/last/all) all select that version.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from functools import wraps
from typing import Iterable

from flask import Blueprint, Response, g, request

from models import TaxiiFeed
from models.user import ApiToken, User
from services.auth import check_password, decode_jwt, hash_api_token
from services.database import db
from services.taxii_collection import (
    DEFAULT_PAGE_SIZE,
    MAX_CONTENT_LENGTH,
    MAX_PAGE_SIZE,
    SUPPORTED_TYPES,
    VERSION_KEYWORDS,
    Page,
    TaxiiQuery,
    TaxiiRecord,
    decode_cursor,
    encode_cursor,
    fetch_page,
    feed_types,
    format_timestamp,
    parse_timestamp,
    record_from_row,
)


taxii_bp = Blueprint("taxii", __name__, url_prefix="/taxii2")

TAXII_MEDIA_TYPE = "application/taxii+json;version=2.1"
STIX_MEDIA_TYPE = "application/stix+json;version=2.1"
API_ROOT_SEGMENT = "default"
API_ROOT_PATH = f"/taxii2/{API_ROOT_SEGMENT}/"

_AUTH_CHALLENGE = 'Basic realm="OFM TAXII", Bearer realm="OFM TAXII"'
_DEFAULT_COLLECTION_TITLE = "OpenFraudMonitoring Intelligence"
_DEFAULT_COLLECTION_DESCRIPTION = "Configured STIX export from the OFM intelligence store."


# ---------------------------------------------------------------------------
# Responses and errors
# ---------------------------------------------------------------------------

class TaxiiError(Exception):
    def __init__(self, status: int, title: str, description: str = "", headers: dict | None = None):
        super().__init__(title)
        self.status = status
        self.title = title
        self.description = description
        self.headers = headers or {}


def taxii_response(payload: dict, status: int = 200, headers: dict | None = None) -> Response:
    body = json.dumps(payload, separators=(",", ":"))
    response = Response(body, status=status, content_type=TAXII_MEDIA_TYPE)
    for name, value in (headers or {}).items():
        response.headers[name] = value
    return response


def _error_response(error: TaxiiError) -> Response:
    payload = {"title": error.title, "http_status": str(error.status)}
    if error.description:
        payload["description"] = error.description
    return taxii_response(payload, error.status, error.headers)


@taxii_bp.errorhandler(TaxiiError)
def _handle_taxii_error(error: TaxiiError):
    return _error_response(error)


@taxii_bp.errorhandler(500)
def _handle_internal_error(_error):
    return _error_response(TaxiiError(500, "Internal Server Error", "The TAXII server failed to process the request."))


# ---------------------------------------------------------------------------
# Content negotiation
# ---------------------------------------------------------------------------

def _accept_is_supported(header: str | None) -> bool:
    """Accept TAXII 2.1 media ranges plus generic JSON/wildcards (browsers, curl)."""
    if not header or not header.strip():
        return True
    for media_range in header.split(","):
        parts = [part.strip() for part in media_range.split(";")]
        media = parts[0].lower()
        params = {}
        for part in parts[1:]:
            key, sep, value = part.partition("=")
            if sep:
                params[key.strip().lower()] = value.strip().strip('"')
        try:
            if float(params.get("q", "1")) <= 0:
                continue
        except ValueError:
            continue
        if media == "application/taxii+json":
            if params.get("version", "2.1") == "2.1":
                return True
        elif media in ("*/*", "application/*", "application/json"):
            return True
    return False


@taxii_bp.before_request
def _negotiate_media_type():
    if not _accept_is_supported(request.headers.get("Accept")):
        raise TaxiiError(
            406,
            "Not Acceptable",
            f"This server only produces {TAXII_MEDIA_TYPE}.",
        )


# ---------------------------------------------------------------------------
# Authentication (HTTP Basic, Bearer API token/JWT, access_token query param)
# ---------------------------------------------------------------------------

def _user_from_token(token: str) -> User | None:
    if not token:
        return None
    api_token = ApiToken.query.filter_by(token_hash=hash_api_token(token), is_active=True).first()
    if api_token is not None:
        if api_token.expires_at and api_token.expires_at < datetime.utcnow():
            return None
        api_token.last_used_at = datetime.utcnow()
        db.session.commit()
        return db.session.get(User, api_token.user_id)
    payload = decode_jwt(token)
    if payload is not None:
        return db.session.get(User, payload.get("sub"))
    return None


def _user_from_basic(encoded: str) -> User | None:
    try:
        decoded = base64.b64decode(encoded.strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    username, sep, password = decoded.partition(":")
    if not sep or not password:
        return None
    user = User.query.filter_by(username=username).first() if username else None
    if user is not None and user.password_hash:
        try:
            if check_password(password, user.password_hash):
                return user
        except ValueError:
            pass
    # Clients that only support Basic auth may send an API token as password.
    return _user_from_token(password)


def _resolve_taxii_user() -> User | None:
    auth_header = request.headers.get("Authorization", "")
    scheme, _, credentials = auth_header.partition(" ")
    if scheme.lower() == "basic":
        user = _user_from_basic(credentials)
    elif scheme.lower() == "bearer":
        user = _user_from_token(credentials.strip())
    else:
        user = _user_from_token((request.args.get("access_token") or "").strip())
    if user is None or not user.is_active:
        return None
    return user


def require_taxii_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _resolve_taxii_user()
        if user is None:
            collection_id = kwargs.get("collection_id")
            if request.method in ("GET", "HEAD"):
                if collection_id:
                    feed = active_feed_by_uuid(collection_id)
                    if feed is not None and getattr(feed, "is_public", False):
                        g.current_user = None
                        return fn(*args, **kwargs)
                elif fn.__name__ in ("api_root", "collections") and _has_public_collections():
                    g.current_user = None
                    return fn(*args, **kwargs)
            raise TaxiiError(
                401,
                "Unauthorized",
                "Valid HTTP Basic or Bearer credentials are required.",
                {"WWW-Authenticate": _AUTH_CHALLENGE},
            )
        g.current_user = user
        return fn(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Query parameters
# ---------------------------------------------------------------------------

def _bad_request(description: str) -> TaxiiError:
    return TaxiiError(400, "Bad Request", description)


def parse_query(match_fields: Iterable[str]) -> TaxiiQuery:
    args = request.args
    for key in args.keys():
        if (key.startswith("match[") or key in ("added_after", "limit", "next")) and len(args.getlist(key)) > 1:
            raise _bad_request(f"Parameter '{key}' must not be repeated.")

    query = TaxiiQuery()

    raw_limit = args.get("limit")
    if raw_limit is not None:
        try:
            limit = int(raw_limit)
        except ValueError:
            raise _bad_request("limit must be a positive integer.") from None
        if limit <= 0:
            raise _bad_request("limit must be a positive integer.")
        query.limit = min(limit, MAX_PAGE_SIZE)

    raw_added_after = args.get("added_after")
    if raw_added_after is not None:
        query.added_after = parse_timestamp(raw_added_after)
        if query.added_after is None:
            raise _bad_request("added_after must be an RFC 3339 timestamp.")

    raw_next = args.get("next")
    if raw_next is not None:
        query.cursor = decode_cursor(raw_next)
        if query.cursor is None:
            raise _bad_request("next is not a valid pagination value.")

    for name in match_fields:
        raw_value = args.get(f"match[{name}]")
        if raw_value is None:
            continue
        values = [item.strip() for item in raw_value.split(",") if item.strip()]
        if not values:
            continue
        if name == "type":
            values = [item.lower() for item in values]
        if name == "version":
            for item in values:
                if item not in VERSION_KEYWORDS and parse_timestamp(item) is None:
                    raise _bad_request(f"Invalid match[version] value '{item}'.")
        query.match[name] = values
    return query


def _object_in_collection(feed: TaxiiFeed, object_id: str) -> bool:
    return bool(fetch_page(feed, TaxiiQuery(limit=1), object_id=object_id).records)


def active_feed_by_uuid(collection_id: str) -> TaxiiFeed | None:
    return TaxiiFeed.query.filter_by(uuid=collection_id, is_active=True, export_format="taxii").first()


def _has_public_collections():
    return TaxiiFeed.query.filter_by(is_active=True, export_format="taxii", is_public=True).first() is not None


def _require_feed(collection_id: str) -> TaxiiFeed:
    feed = active_feed_by_uuid(collection_id)
    if feed is None:
        raise TaxiiError(404, "Not Found", "Unknown TAXII collection.")
    return feed


def _collection_resource(feed: TaxiiFeed) -> dict:
    return {
        "id": feed.uuid,
        "title": feed.name or _DEFAULT_COLLECTION_TITLE,
        "description": feed.description or _DEFAULT_COLLECTION_DESCRIPTION,
        "can_read": True,
        "can_write": False,
        "media_types": [STIX_MEDIA_TYPE],
    }


def _paged_resource(page: Page, items_key: str, items: list, include_next: bool = True) -> dict:
    payload: dict = {"more": page.more}
    next_value = page.next if include_next else None
    if next_value:
        payload["next"] = next_value
    if items:
        payload[items_key] = items
    return payload


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@taxii_bp.route("/", methods=["GET"])
def discovery():
    return taxii_response({
        "title": "OpenFraudMonitoring TAXII",
        "description": "Read-only TAXII 2.1 server for OFM STIX 2.1 intelligence.",
        "default": API_ROOT_PATH,
        "api_roots": [API_ROOT_PATH],
    })


@taxii_bp.route(f"/{API_ROOT_SEGMENT}/", methods=["GET"])
@require_taxii_auth
def api_root():
    return taxii_response({
        "title": "OFM TAXII API Root",
        "description": "Read-only STIX 2.1 collections configured as OFM export feeds.",
        "versions": [TAXII_MEDIA_TYPE],
        "max_content_length": MAX_CONTENT_LENGTH,
    })


@taxii_bp.route(f"/{API_ROOT_SEGMENT}/status/<status_id>/", methods=["GET"])
@require_taxii_auth
def status(status_id: str):
    raise TaxiiError(404, "Not Found", "This read-only API root does not create status resources.")


@taxii_bp.route(f"/{API_ROOT_SEGMENT}/collections/", methods=["GET"])
@require_taxii_auth
def collections():
    query = TaxiiFeed.query.filter_by(is_active=True, export_format="taxii")
    if g.current_user is None:
        query = query.filter_by(is_public=True)
    feeds = query.order_by(TaxiiFeed.id.asc()).all()
    if not feeds:
        return taxii_response({})
    return taxii_response({"collections": [_collection_resource(feed) for feed in feeds]})


@taxii_bp.route(f"/{API_ROOT_SEGMENT}/collections/<collection_id>/", methods=["GET"])
@require_taxii_auth
def collection_detail(collection_id: str):
    return taxii_response(_collection_resource(_require_feed(collection_id)))


@taxii_bp.route(f"/{API_ROOT_SEGMENT}/collections/<collection_id>/manifest/", methods=["GET"])
@require_taxii_auth
def collection_manifest(collection_id: str):
    feed = _require_feed(collection_id)
    page = fetch_page(feed, parse_query(("id", "type", "version", "spec_version")), whole_date_groups=True)
    manifest = [
        {
            "id": record.stix_id,
            "date_added": format_timestamp(record.date_added),
            "version": record.version,
            "media_type": f"application/stix+json;version={record.spec_version}",
        }
        for record in page.records
    ]
    return taxii_response(_paged_resource(page, "objects", manifest, include_next=False), headers=page.headers)


@taxii_bp.route(f"/{API_ROOT_SEGMENT}/collections/<collection_id>/objects/", methods=["GET"])
@require_taxii_auth
def collection_objects(collection_id: str):
    feed = _require_feed(collection_id)
    page = fetch_page(feed, parse_query(("id", "type", "version", "spec_version")))
    objects = [record.raw for record in page.records]
    return taxii_response(_paged_resource(page, "objects", objects), headers=page.headers)


@taxii_bp.route(f"/{API_ROOT_SEGMENT}/collections/<collection_id>/objects/", methods=["POST"])
@require_taxii_auth
def add_objects(collection_id: str):
    _require_feed(collection_id)
    raise TaxiiError(403, "Forbidden", "This collection is read-only (can_write is false).")


@taxii_bp.route(f"/{API_ROOT_SEGMENT}/collections/<collection_id>/objects/<object_id>/", methods=["GET"])
@require_taxii_auth
def collection_object(collection_id: str, object_id: str):
    feed = _require_feed(collection_id)
    query = parse_query(("version", "spec_version"))
    if not _object_in_collection(feed, object_id):
        raise TaxiiError(404, "Not Found", "Unknown object in this collection.")
    page = fetch_page(feed, query, object_id=object_id)
    objects = [record.raw for record in page.records]
    return taxii_response(_paged_resource(page, "objects", objects), headers=page.headers)


@taxii_bp.route(f"/{API_ROOT_SEGMENT}/collections/<collection_id>/objects/<object_id>/", methods=["DELETE"])
@require_taxii_auth
def delete_object(collection_id: str, object_id: str):
    _require_feed(collection_id)
    raise TaxiiError(403, "Forbidden", "This collection is read-only (can_write is false).")


@taxii_bp.route(f"/{API_ROOT_SEGMENT}/collections/<collection_id>/objects/<object_id>/versions/", methods=["GET"])
@require_taxii_auth
def object_versions(collection_id: str, object_id: str):
    feed = _require_feed(collection_id)
    query = parse_query(("spec_version",))
    if not _object_in_collection(feed, object_id):
        raise TaxiiError(404, "Not Found", "Unknown object in this collection.")
    page = fetch_page(feed, query, object_id=object_id, whole_date_groups=True)
    return taxii_response(
        _paged_resource(page, "versions", [record.version for record in page.records], include_next=False),
        headers=page.headers,
    )


@taxii_bp.route("/<path:_unknown>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def not_found(_unknown: str):
    raise TaxiiError(404, "Not Found", "Unknown TAXII endpoint or API root.")

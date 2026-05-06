"""
Connector observability routes — used by the /logging page.

Endpoints
---------

GET /api/connectors/status
    Returns the list of known connectors with:
      - name
      - mode (manual/auto/both)
      - last_seen (ISO timestamp, or None)
      - healthy (bool — heartbeat seen in the last 30s)
      - request_queue_depth, response_queue_depth (best-effort)

GET /api/connectors/logs?tail=100
    Returns the most recent log entries (WARNING+) shipped by all
    components via Redis.
"""

import json
import logging
from datetime import datetime
from typing import List
from urllib.parse import urlparse

import requests
from flask import Blueprint, jsonify, request

from services.event_queue import get_redis
from services.mq import queue_depth, request_queue, RESPONSE_QUEUE
from services.auth import require_auth
from config import Config

logger = logging.getLogger(__name__)

connectors_bp = Blueprint("connectors", __name__, url_prefix="/api/connectors")


HEARTBEAT_TTL_SECONDS = 30


def _list_connectors() -> List[str]:
    r = get_redis()
    names = set()
    try:
        for key in r.scan_iter(match="ofm:connector:*:heartbeat"):
            parts = key.decode("utf-8").split(":")
            if len(parts) >= 4:
                names.add(parts[2])
        for key in r.scan_iter(match="ofm:connector:*:mode"):
            parts = key.decode("utf-8").split(":")
            if len(parts) >= 4:
                names.add(parts[2])
    except Exception as e:
        logger.warning("connector listing failed: %s", e)
    return sorted(names)


def _connector_info(name: str) -> dict:
    r = get_redis()
    try:
        last_raw = r.get(f"ofm:connector:{name}:heartbeat")
        last_seen_ts = int(last_raw) if last_raw else None
    except Exception:
        last_seen_ts = None

    try:
        mode_raw = r.get(f"ofm:connector:{name}:mode")
        mode = mode_raw.decode("utf-8") if mode_raw else "manual"
    except Exception:
        mode = "manual"

    try:
        type_raw = r.get(f"ofm:connector:{name}:type")
        connector_type = type_raw.decode("utf-8") if type_raw else "enricher"
    except Exception:
        connector_type = "enricher"

    try:
        scope_raw = r.get(f"ofm:connector:{name}:scope")
        scope = json.loads(scope_raw.decode("utf-8")) if scope_raw else []
    except Exception:
        scope = []

    now_ts = int(datetime.utcnow().timestamp())
    healthy = last_seen_ts is not None and (now_ts - last_seen_ts) <= HEARTBEAT_TTL_SECONDS

    return {
        "name": name,
        "mode": mode,
        "connector_type": connector_type,
        "scope": scope,
        "healthy": healthy,
        "last_seen": datetime.utcfromtimestamp(last_seen_ts).isoformat() + "Z" if last_seen_ts else None,
        "last_seen_age_seconds": (now_ts - last_seen_ts) if last_seen_ts else None,
        "request_queue_depth": queue_depth(request_queue(name)),
    }


@connectors_bp.route("/status", methods=["GET"])
@require_auth
def status():
    connectors = [_connector_info(name) for name in _list_connectors()]
    return jsonify({
        "connectors": connectors,
        "queues": {
            "responses": queue_depth(RESPONSE_QUEUE),
            "events": _list_length("ofm:events"),
        },
    }), 200


@connectors_bp.route("/enrichers", methods=["GET"])
@require_auth
def enrichers():
    """Return enricher connectors that support a given entity type.

    Query params:
        entity_type  – STIX type to filter by (e.g. ipv4-addr). Optional;
                       if omitted, all enrichers are returned.
    """
    entity_type = (request.args.get("entity_type") or "").strip().lower()
    all_connectors = [_connector_info(name) for name in _list_connectors()]
    enrichers_list = [
        c for c in all_connectors
        if c["connector_type"] == "enricher"
        and c["healthy"]
        and (not entity_type or entity_type in c["scope"])
    ]
    return jsonify({"enrichers": enrichers_list}), 200


def _list_length(key: str):
    try:
        return get_redis().llen(key)
    except Exception:
        return None


@connectors_bp.route("/logs", methods=["GET"])
@require_auth
def logs():
    try:
        tail = max(1, min(int(request.args.get("tail", "100")), 500))
    except ValueError:
        tail = 100

    r = get_redis()
    try:
        raw = r.lrange("ofm:logs", 0, tail - 1)
    except Exception as e:
        return jsonify({"error": str(e), "entries": []}), 200

    entries = []
    for item in raw:
        try:
            entries.append(json.loads(item.decode("utf-8")))
        except Exception:
            continue
    return jsonify({"entries": entries, "count": len(entries)}), 200
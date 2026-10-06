"""
Intel routes — ad-hoc IP lookups and connector ingest endpoint.

Endpoints
---------

GET /api/intel/ip/<value>
    Return cached intel for an IP value: the observable record, AS,
    country, indicators (and what they indicate), all relationships.
    Decayed flag set when older than INTEL_DECAY_DAYS.

POST /api/intel/lookup
    Body: {"connector": "opencti", "value": "1.2.3.4"}
    Enqueues an intel-lookup request to the named connector via RabbitMQ.

POST /api/intel/ingest
    Auth:   Authorization: Bearer <CONNECTOR_TOKEN>
    Body:   {"connector": "opencti", "value": "...", "stix_bundle": {...}}
    Direct fallback HTTP path; persists the bundle into the STIX tables.
"""

import ipaddress
import json
from datetime import datetime, timedelta
import logging

from flask import Blueprint, request, jsonify, current_app, g
from sqlalchemy import and_, func, or_

from services.database import db
from services.mq import publish_intel_request
from services.intel_ingest import ingest_bundle
from services.auth import require_auth, require_role
from services.stix_filters import TYPE_TO_MODEL, get_filter_schema, apply_filters
from models import (
    Session,
    StixRelationship,
)

intel_bp = Blueprint("intel", __name__, url_prefix="/api/intel")

logger = logging.getLogger(__name__)

_SCO_TYPES = {"ipv4-addr", "ipv6-addr", "user-agent"}

def _stix_id_type(stix_id: str) -> str:
    return (stix_id or "").split("--", 1)[0]


def _resolve(stix_id: str):
    """Look up a STIX object across the per-type tables by stix_id."""
    t = _stix_id_type(stix_id)
    Model = TYPE_TO_MODEL.get(t)
    if not Model:
        return None
    return Model.query.filter_by(stix_id=stix_id).first()


def _entity_dict(row, stix_type=None):
    if row is None:
        return None
    stix_type = stix_type or _stix_id_type(row.stix_id)
    return {**row.to_dict(), "stix_type": stix_type}


def _session_condition(observable):
    stix_type = observable.get("stix_type")
    row_id = (observable.get("platform") or {}).get("id")
    if row_id is None:
        return None
    if stix_type in ("ipv4-addr", "ipv6-addr"):
        return and_(Session.ip_observable_id == row_id, Session.ip_observable_type == stix_type)
    if stix_type == "user-agent":
        return Session.user_agent_observable_id == row_id
    return None


def _sessions_for_observables(observables):
    conditions = [
        condition for observable in observables
        if (condition := _session_condition(observable)) is not None
    ]
    if not conditions:
        return None
    return Session.query.filter(or_(*conditions))


def _session_summary(observables):
    query = _sessions_for_observables(observables)
    if query is None:
        return {"count": 0, "first_seen": None, "last_seen": None}
    count = query.with_entities(Session.id).distinct().count()
    first_seen, last_seen = query.with_entities(
        func.min(Session.first_seen), func.max(Session.last_seen),
    ).one()
    return {
        "count": count,
        "first_seen": first_seen if first_seen and first_seen > 0 else None,
        "last_seen": last_seen if last_seen and last_seen > 0 else None,
    }


def _apply_decay(rows, days: int):
    """Mark/unmark `decayed` based on last_refreshed_at age.  Commits."""
    threshold = datetime.utcnow() - timedelta(days=days)
    changed = False
    for r in rows:
        ref = r.last_refreshed_at or r.created_at_platform
        should_decay = bool(ref and ref < threshold)
        if r.decayed != should_decay:
            r.decayed = should_decay
            changed = True
    if changed:
        db.session.commit()


def _detect_ip_model(ip: str):
    try:
        v = ipaddress.ip_address(ip).version
    except (ValueError, TypeError):
        return None
    return TYPE_TO_MODEL["ipv4-addr"] if v == 4 else TYPE_TO_MODEL["ipv6-addr"]


def _build_entity_response(obs, stix_type: str):
    """Build the intel response with direct, indicator, and observable context separated."""
    days = int(current_app.config.get("INTEL_DECAY_DAYS", 7))

    rels = StixRelationship.query.filter(
        (StixRelationship.source_ref == obs.stix_id)
        | (StixRelationship.target_ref == obs.stix_id)
    ).all()

    # For an SCO, add its based-on indicators and each indicator's indications.
    based_on_rels = [
        r.source_ref
        for r in rels
        if r.relationship_type == "based-on" and r.target_ref == obs.stix_id
    ]
    indirect_rels = []
    if based_on_rels:
        indirect_rels = StixRelationship.query.filter(
            StixRelationship.relationship_type == "indicates",
            StixRelationship.source_ref.in_(based_on_rels),
        ).all()

    _apply_decay([obs], days)

    all_rels = rels + indirect_rels
    referenced_ids = set()
    for r in all_rels:
        referenced_ids.add(r.source_ref)
        referenced_ids.add(r.target_ref)
    referenced_ids.discard(obs.stix_id)

    referenced = {}
    related_objs = []
    for sid in referenced_ids:
        ro = _resolve(sid)
        if ro is None:
            continue
        related_objs.append(ro)
        referenced[sid] = {
            **ro.to_dict(),
            "stix_type": _stix_id_type(sid),
        }
    _apply_decay(related_objs, days)

    # Convenience extracts: AS + country directly belonging-to / located-at.
    autonomous_system = None
    country = None
    summarized_rel_ids = set()
    for r in rels:
        if r.relationship_type == "belongs-to" and r.source_ref == obs.stix_id:
            tgt = referenced.get(r.target_ref)
            if tgt and tgt["stix_type"] == "autonomous-system":
                autonomous_system = tgt
                summarized_rel_ids.add(r.stix_id)
        elif r.relationship_type == "located-at" and r.source_ref == obs.stix_id:
            tgt = referenced.get(r.target_ref)
            if tgt and tgt["stix_type"] == "location":
                country = tgt
                summarized_rel_ids.add(r.stix_id)

    obs_dict = {**obs.to_dict(), "stix_type": stix_type}

    known_malicious_behavior = []
    if stix_type in _SCO_TYPES:
        indicates_by_indicator = {}
        for rel in indirect_rels:
            indicator = referenced.get(rel.source_ref)
            target = referenced.get(rel.target_ref)
            if (
                not indicator
                or indicator["stix_object"].get("revoked") is True
                or not target
            ):
                continue
            indicates_by_indicator.setdefault(rel.source_ref, []).append(rel)
            summarized_rel_ids.add(rel.stix_id)
        for rel in rels:
            if rel.relationship_type != "based-on" or rel.target_ref != obs.stix_id:
                continue
            indicator = referenced.get(rel.source_ref)
            if not indicator or indicator["stix_object"].get("revoked") is True:
                continue
            summarized_rel_ids.add(rel.stix_id)
            indicator_rels = [
                item for item in indicates_by_indicator.get(rel.source_ref, [])
                if item.target_ref in referenced
            ]
            target_ids = dict.fromkeys(item.target_ref for item in indicator_rels)
            targets = [referenced[target_id] for target_id in target_ids]
            latest_rel = max(
                indicator_rels,
                key=lambda item: item.created_at_platform or datetime.min,
                default=None,
            )
            latest_indicated = None
            if latest_rel:
                latest_indicated = {
                    "entity": referenced[latest_rel.target_ref],
                    "indicated_at": latest_rel.created_at_platform.isoformat()
                    if latest_rel.created_at_platform else None,
                }
            known_malicious_behavior.append({
                "indicator": indicator,
                "indicates": targets,
                "latest_indicated": latest_indicated,
            })

    based_on_observables = []
    indicated_entities = []
    if stix_type == "indicator":
        based_on_ids = set()
        indicated_ids = set()
        for rel in rels:
            if rel.source_ref != obs.stix_id:
                continue
            if rel.relationship_type == "based-on":
                target = referenced.get(rel.target_ref)
                if target and target["stix_type"] in _SCO_TYPES and rel.target_ref not in based_on_ids:
                    based_on_observables.append(target)
                    based_on_ids.add(rel.target_ref)
                    summarized_rel_ids.add(rel.stix_id)
            elif rel.relationship_type == "indicates":
                target = referenced.get(rel.target_ref)
                if target and rel.target_ref not in indicated_ids:
                    indicated_entities.append(target)
                    indicated_ids.add(rel.target_ref)
                    summarized_rel_ids.add(rel.stix_id)

    session_observables = based_on_observables if stix_type == "indicator" else (
        [obs_dict] if stix_type in _SCO_TYPES else []
    )
    observable_sessions = _session_summary(session_observables)

    return {
        "found": True,
        "value": obs.value,
        "observable": obs_dict,
        "autonomous_system": autonomous_system,
        "country": country,
        "session_count": observable_sessions["count"],
        "session_count_scope": "based-on observable(s)" if stix_type == "indicator" else "this observable" if stix_type in _SCO_TYPES else None,
        "first_seen": observable_sessions["first_seen"],
        "last_seen": observable_sessions["last_seen"],
        "based_on_observables": based_on_observables,
        "indicates": indicated_entities,
        "known_malicious_behavior": known_malicious_behavior,
        "relationships": [
            {**r.to_dict(),
             "source": referenced.get(r.source_ref) if r.source_ref != obs.stix_id else obs_dict,
             "target": referenced.get(r.target_ref) if r.target_ref != obs.stix_id else obs_dict}
            for r in all_rels if r.stix_id not in summarized_rel_ids
        ],
        "decay_days": days,
    }


@intel_bp.route("/ip/<path:value>", methods=["GET"])
@require_auth
def get_ip_intel(value):
    """Return everything we know about an IP from the local STIX cache."""
    Model = _detect_ip_model(value)
    if Model is None:
        return jsonify({"error": "invalid IP address"}), 400

    obs = Model.query.filter_by(value=value).first()
    if obs is None:
        return jsonify({"found": False, "value": value}), 200

    stix_type = "ipv4-addr" if Model is TYPE_TO_MODEL["ipv4-addr"] else "ipv6-addr"
    return jsonify(_build_entity_response(obs, stix_type)), 200


@intel_bp.route("/entity", methods=["GET"])
@require_auth
def get_entity_intel():
    """Generic entity lookup by STIX type + value.

    Query params:
        type   – STIX type key (e.g. ipv4-addr, user-agent)
        value  – value to search for (exact match)
    """
    stix_type = (request.args.get("type") or "").strip().lower()
    value = (request.args.get("value") or "").strip()

    if not stix_type or not value:
        return jsonify({"error": "type and value are required"}), 400

    Model = TYPE_TO_MODEL.get(stix_type)
    if Model is None:
        return jsonify({"error": f"unknown entity type: {stix_type}"}), 400

    obs = Model.query.filter_by(value=value).first()
    if obs is None:
        return jsonify({"found": False, "value": value, "type": stix_type}), 200

    return jsonify(_build_entity_response(obs, stix_type)), 200


@intel_bp.route("/filter-schema", methods=["GET"])
@require_auth
def filter_schema():
    """Return filter schema for an entity type (or all known types)."""
    stix_type = (request.args.get("type") or "").strip().lower()
    if stix_type:
        schema = get_filter_schema(stix_type)
        if schema is None:
            return jsonify({"error": f"unknown entity type: {stix_type}"}), 400
        return jsonify({"type": stix_type, "fields": schema}), 200

    all_schemas = {}
    for t in TYPE_TO_MODEL:
        all_schemas[t] = get_filter_schema(t) or []
    return jsonify({"schemas": all_schemas}), 200


@intel_bp.route("/types", methods=["GET"])
@require_auth
def entity_types():
    """Return the list of STIX entity types that have at least one record."""
    available = []
    for stix_type, Model in TYPE_TO_MODEL.items():
        count = Model.query.count()
        if count > 0:
            available.append({"type": stix_type, "count": count})
    return jsonify({"types": available}), 200


@intel_bp.route("/entities", methods=["GET"])
@require_auth
def list_entities():
    """Return the latest N entities of a given STIX type.

    Query params:
        type    – STIX type key (e.g. ipv4-addr, user-agent)
        limit   – max results (default 25, max 500)
        logic   – AND | OR (default AND)
        filters – JSON array of conditions [{field, op, value}, ...]
    """
    stix_type = (request.args.get("type") or "").strip().lower()
    logic = (request.args.get("logic") or "AND").strip().upper()
    filters_raw = request.args.get("filters", "[]")

    try:
        limit = min(max(1, int(request.args.get("limit", "25"))), 500)
    except (ValueError, TypeError):
        limit = 25

    try:
        filters = json.loads(filters_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "invalid filters JSON"}), 400

    if not isinstance(filters, list):
        return jsonify({"error": "filters must be an array"}), 400

    if logic not in ("AND", "OR"):
        return jsonify({"error": "logic must be AND or OR"}), 400

    Model = TYPE_TO_MODEL.get(stix_type)
    if Model is None:
        return jsonify({"error": f"unknown entity type: {stix_type}"}), 400

    days = int(current_app.config.get("INTEL_DECAY_DAYS", 7))
    query = Model.query
    query, err = apply_filters(query, stix_type, filters, logic=logic)
    if err:
        return jsonify({"error": err}), 400

    rows = query.order_by(Model.created_at_platform.desc()).limit(limit).all()
    _apply_decay(rows, days)

    return jsonify({
        "type": stix_type,
        "logic": logic,
        "filters_applied": len(filters),
        "entities": [
            {**r.to_dict(), "stix_type": stix_type}
            for r in rows
        ],
    }), 200


@intel_bp.route("/lookup", methods=["POST"])
@require_auth
def lookup():
    body = request.get_json(silent=True) or {}
    connector = (body.get("connector") or "opencti").strip()
    value = (body.get("value") or "").strip()
    if not value:
        return jsonify({"error": "value is required"}), 400

    request_id = publish_intel_request(connector, value, request_type="ip_lookup")
    if not request_id:
        return jsonify({"error": "Failed to enqueue request"}), 502
    return jsonify({"request_id": request_id, "connector": connector}), 202


@intel_bp.route("/entity-sessions", methods=["GET"])
@require_auth
def get_entity_sessions():
    """Get the latest sessions linked to a STIX entity.
    
    Query params:
        type    – STIX type key (e.g. ipv4-addr, user-agent)
        value   – value to search for (exact match)
        limit   – max results (default 10, max 100)
    """
    stix_type = (request.args.get("type") or "").strip().lower()
    value = (request.args.get("value") or "").strip()
    
    if not stix_type or not value:
        return jsonify({"error": "type and value are required"}), 400
    
    Model = TYPE_TO_MODEL.get(stix_type)
    if Model is None:
        return jsonify({"error": f"unknown entity type: {stix_type}"}), 400
    
    obs = Model.query.filter_by(value=value).first()
    if obs is None:
        return jsonify({"sessions": []}), 200
    
    try:
        limit = min(max(1, int(request.args.get("limit", "10"))), 100)
    except (ValueError, TypeError):
        limit = 10
    
    observables = []
    if stix_type in _SCO_TYPES:
        observables.append(_entity_dict(obs, stix_type))
    elif stix_type == "indicator":
        based_on = StixRelationship.query.filter_by(
            relationship_type="based-on", source_ref=obs.stix_id,
        ).all()
        for relationship in based_on:
            observable_type = _stix_id_type(relationship.target_ref)
            if observable_type not in _SCO_TYPES:
                continue
            observable = _resolve(relationship.target_ref)
            if observable is not None:
                observables.append(_entity_dict(observable, observable_type))

    session_query = _sessions_for_observables(observables)
    sessions = (
        session_query.order_by(Session.last_seen.desc()).limit(limit).all()
        if session_query is not None else []
    )
    
    return jsonify({
        "entity_type": stix_type,
        "entity_value": value,
        "sessions": [s.to_dict() for s in sessions],
    }), 200


@intel_bp.route("/ingest", methods=["POST"])
@require_auth
@require_role("connector", "admin")
def ingest():
    body = request.get_json(silent=True) or {}
    bundle = body.get("stix_bundle") or {}
    count = ingest_bundle(bundle, source_connector_id=g.current_user.id)
    return jsonify({"ok": True, "objects_ingested": count}), 200

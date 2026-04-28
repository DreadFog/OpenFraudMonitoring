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
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, current_app

from services.database import db
from services.mq import publish_intel_request
from services.intel_ingest import ingest_bundle
from models import (
    StixIPv4Addr,
    StixIPv6Addr,
    StixAutonomousSystem,
    StixCountry,
    StixIndicator,
    StixMalware,
    StixCampaign,
    StixIntrusionSet,
    StixRelationship,
)

intel_bp = Blueprint("intel", __name__, url_prefix="/api/intel")


# Map relationship target / source types to their backing model.
_TYPE_TO_MODEL = {
    "ipv4-addr": StixIPv4Addr,
    "ipv6-addr": StixIPv6Addr,
    "autonomous-system": StixAutonomousSystem,
    "location": StixCountry,
    "indicator": StixIndicator,
    "malware": StixMalware,
    "campaign": StixCampaign,
    "intrusion-set": StixIntrusionSet,
}


def _stix_id_type(stix_id: str) -> str:
    return (stix_id or "").split("--", 1)[0]


def _resolve(stix_id: str):
    """Look up a STIX object across the per-type tables by stix_id."""
    t = _stix_id_type(stix_id)
    Model = _TYPE_TO_MODEL.get(t)
    if not Model:
        return None
    return Model.query.filter_by(stix_id=stix_id).first()


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
    return StixIPv4Addr if v == 4 else StixIPv6Addr


@intel_bp.route("/ip/<path:value>", methods=["GET"])
def get_ip_intel(value):
    """Return everything we know about an IP from the local STIX cache."""
    Model = _detect_ip_model(value)
    if Model is None:
        return jsonify({"error": "invalid IP address"}), 400

    obs = Model.query.filter_by(value=value).first()
    if obs is None:
        return jsonify({"found": False, "value": value}), 200

    days = int(current_app.config.get("INTEL_DECAY_DAYS", 7))

    # ── Direct relationships involving this observable ──
    rels = StixRelationship.query.filter(
        (StixRelationship.source_ref == obs.stix_id)
        | (StixRelationship.target_ref == obs.stix_id)
    ).all()

    # Indirect: indicators -> malware/campaign/intrusion-set
    indicator_ids = [
        r.source_ref
        for r in rels
        if r.relationship_type == "based-on" and r.target_ref == obs.stix_id
    ]
    indirect_rels = []
    if indicator_ids:
        indirect_rels = StixRelationship.query.filter(
            StixRelationship.relationship_type == "indicates",
            StixRelationship.source_ref.in_(indicator_ids),
        ).all()

    all_rels = rels + indirect_rels
    _apply_decay([obs] + all_rels, days)

    # Resolve referenced objects.
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
    for r in rels:
        if r.relationship_type == "belongs-to" and r.source_ref == obs.stix_id:
            tgt = referenced.get(r.target_ref)
            if tgt and tgt["stix_type"] == "autonomous-system":
                autonomous_system = tgt
        elif r.relationship_type == "located-at" and r.source_ref == obs.stix_id:
            tgt = referenced.get(r.target_ref)
            if tgt and tgt["stix_type"] == "location":
                country = tgt

    return jsonify({
        "found": True,
        "value": value,
        "observable": {
            **obs.to_dict(),
            "stix_type": _stix_id_type(obs.stix_id),
        },
        "autonomous_system": autonomous_system,
        "country": country,
        "relationships": [
            {**r.to_dict(),
             "source": referenced.get(r.source_ref) if r.source_ref != obs.stix_id else {**obs.to_dict(), "stix_type": _stix_id_type(obs.stix_id)},
             "target": referenced.get(r.target_ref) if r.target_ref != obs.stix_id else {**obs.to_dict(), "stix_type": _stix_id_type(obs.stix_id)}}
            for r in all_rels
        ],
        "decay_days": days,
    }), 200


@intel_bp.route("/lookup", methods=["POST"])
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


@intel_bp.route("/ingest", methods=["POST"])
def ingest():
    auth_header = request.headers.get("Authorization", "")
    expected = current_app.config.get("CONNECTOR_TOKEN", "")
    if not auth_header.startswith("Bearer ") or auth_header[len("Bearer "):].strip() != expected:
        return jsonify({"error": "unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    bundle = body.get("stix_bundle") or {}
    count = ingest_bundle(bundle)
    return jsonify({"ok": True, "objects_ingested": count}), 200

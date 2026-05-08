"""
Custom filter registry — manually maintained filters that extend the
auto-generated FPScanner schema.

Each custom filter bundles:
  - schema metadata  (name, label, type)  → exposed to the frontend filter builder
  - a handler(query, op, value)           → called by build_session_query in rules/engine.py

To add a new custom filter:
  1. Write a handler function:  def _handle_xxx(query, op, value) -> query
  2. Call register_custom_filter(...) at module level.

The schema_registry imports CUSTOM_FIELDS from here and merges them with
the auto-generated FPScanner fields.  rules/engine.py calls get_custom_handler()
to dispatch filters that don't map to a simple model column.
"""

import ipaddress
from sqlalchemy import and_, or_

# ── Registry ─────────────────────────────────────────────────────────────────

# Each entry:  { "name": ..., "label": ..., "type": ..., "handler": callable }
_CUSTOM_FILTERS: dict[str, dict] = {}


def register_custom_filter(name: str, label: str, field_type: str, handler,
                           suggest=None, aggregate=None):
    """
    Register a custom filter.

    Args:
        name:       unique filter identifier (used in filter JSON from frontend)
        label:      human-readable label shown in the filter builder
        field_type: one of "string", "number", "boolean", "date"
        handler:    callable(query, op, value) -> query
                    Receives the current SQLAlchemy Session query and must
                    return a (possibly filtered) query.
        suggest:    optional callable(q: str) -> list[str]
                    Returns autocomplete suggestions for the filter builder.
                    If None, default behaviour per type is used (e.g. true/false
                    for booleans, empty list for numbers).
        aggregate:  optional callable(session_ids: list[int], limit: int)
                    -> list[{"value": str, "count": int}]
                    Returns grouped counts for widget aggregation (pie, histogram, etc.).
                    If None, the field cannot be used as a widget grouping field.
    """
    _CUSTOM_FILTERS[name] = {
        "name": name,
        "label": label,
        "type": field_type,
        "handler": handler,
        "suggest": suggest,
        "aggregate": aggregate,
    }


def get_custom_handler(field_name: str):
    """Return the handler for a custom filter, or None if it's not custom."""
    entry = _CUSTOM_FILTERS.get(field_name)
    return entry["handler"] if entry else None


def get_custom_fields() -> list[dict]:
    """
    Return schema metadata for all registered custom filters.
    Used by schema_registry to merge into SCHEMA_FIELDS.
    """
    return [
        {"name": f["name"], "label": f["label"], "type": f["type"]}
        for f in _CUSTOM_FILTERS.values()
    ]


def get_custom_suggestions(field_name: str, q: str) -> list[str] | None:
    """
    Return autocomplete suggestions for a custom filter.
    Returns None if the filter has no suggest function (caller should
    fall back to default behaviour for the field type).
    """
    entry = _CUSTOM_FILTERS.get(field_name)
    if not entry or entry["suggest"] is None:
        return None
    return entry["suggest"](q)


def get_custom_aggregate(field_name: str, session_ids, limit: int):
    """
    Return grouped aggregation for a custom filter field.
    Returns None if the filter has no aggregate function.
    Returns list of {"value": str, "count": int} otherwise.
    """
    entry = _CUSTOM_FILTERS.get(field_name)
    if not entry or entry["aggregate"] is None:
        return None
    return entry["aggregate"](session_ids, limit)


# ── Suggest helpers ────────────────────────────────────────────────────────────


def _suggest_as(q: str) -> list[str]:
    """Suggest AS numbers from the STIX store."""
    from models import StixAutonomousSystem
    query = StixAutonomousSystem.query
    if q:
        query = query.filter(StixAutonomousSystem.value.ilike(f"%{q}%"))
    rows = query.order_by(StixAutonomousSystem.value).limit(20).all()
    return [r.value for r in rows]


def _suggest_country(q: str) -> list[str]:
    """Suggest country codes from the STIX store."""
    from models import StixCountry
    query = StixCountry.query
    if q:
        query = query.filter(StixCountry.value.ilike(f"%{q}%"))
    rows = query.order_by(StixCountry.value).limit(20).all()
    return [r.value for r in rows]


# ── Aggregate helpers ──────────────────────────────────────────────────────────


def _aggregate_ip_country(session_ids, limit: int):
    """Group sessions by IP country via STIX relationships."""
    from collections import Counter
    from models import Session, StixIPv4Addr, StixIPv6Addr, StixRelationship, StixCountry

    sessions = Session.query.filter(Session.id.in_(session_ids)).all()
    counter = Counter()

    # Build a map: ip_observable (type, id) -> session count
    obs_keys = set()
    for s in sessions:
        if s.ip_observable_id and s.ip_observable_type:
            obs_keys.add((s.ip_observable_type, s.ip_observable_id))

    if not obs_keys:
        return []

    # Resolve observable IDs -> STIX IDs
    ipv4_id_map = {}  # db id -> stix_id
    ipv6_id_map = {}
    ipv4_ids = [oid for otype, oid in obs_keys if otype == "ipv4-addr"]
    ipv6_ids = [oid for otype, oid in obs_keys if otype == "ipv6-addr"]
    if ipv4_ids:
        for o in StixIPv4Addr.query.filter(StixIPv4Addr.id.in_(ipv4_ids)).all():
            ipv4_id_map[o.id] = o.stix_id
    if ipv6_ids:
        for o in StixIPv6Addr.query.filter(StixIPv6Addr.id.in_(ipv6_ids)).all():
            ipv6_id_map[o.id] = o.stix_id

    # Build map: stix_id -> list of session ids
    stix_to_sessions = {}
    for s in sessions:
        if s.ip_observable_type == "ipv4-addr":
            sid = ipv4_id_map.get(s.ip_observable_id)
        elif s.ip_observable_type == "ipv6-addr":
            sid = ipv6_id_map.get(s.ip_observable_id)
        else:
            continue
        if sid:
            stix_to_sessions.setdefault(sid, []).append(s.id)

    if not stix_to_sessions:
        return []

    # Find located-at relationships for these IPs
    all_stix_ids = list(stix_to_sessions.keys())
    rels = StixRelationship.query.filter(
        StixRelationship.source_ref.in_(all_stix_ids),
        StixRelationship.relationship_type == "located-at",
    ).all()

    # Resolve country targets
    country_stix_ids = {r.target_ref for r in rels}
    country_map = {}
    if country_stix_ids:
        for c in StixCountry.query.filter(StixCountry.stix_id.in_(country_stix_ids)).all():
            country_map[c.stix_id] = c.value

    for r in rels:
        country = country_map.get(r.target_ref)
        if country:
            counter[country] += len(stix_to_sessions.get(r.source_ref, []))

    return [
        {"value": val, "count": cnt}
        for val, cnt in counter.most_common(limit)
    ]


def _aggregate_ip_as(session_ids, limit: int):
    """Group sessions by AS number via STIX relationships."""
    from collections import Counter
    from models import Session, StixIPv4Addr, StixIPv6Addr, StixRelationship, StixAutonomousSystem

    sessions = Session.query.filter(Session.id.in_(session_ids)).all()
    counter = Counter()

    obs_keys = set()
    for s in sessions:
        if s.ip_observable_id and s.ip_observable_type:
            obs_keys.add((s.ip_observable_type, s.ip_observable_id))

    if not obs_keys:
        return []

    ipv4_id_map = {}
    ipv6_id_map = {}
    ipv4_ids = [oid for otype, oid in obs_keys if otype == "ipv4-addr"]
    ipv6_ids = [oid for otype, oid in obs_keys if otype == "ipv6-addr"]
    if ipv4_ids:
        for o in StixIPv4Addr.query.filter(StixIPv4Addr.id.in_(ipv4_ids)).all():
            ipv4_id_map[o.id] = o.stix_id
    if ipv6_ids:
        for o in StixIPv6Addr.query.filter(StixIPv6Addr.id.in_(ipv6_ids)).all():
            ipv6_id_map[o.id] = o.stix_id

    stix_to_sessions = {}
    for s in sessions:
        if s.ip_observable_type == "ipv4-addr":
            sid = ipv4_id_map.get(s.ip_observable_id)
        elif s.ip_observable_type == "ipv6-addr":
            sid = ipv6_id_map.get(s.ip_observable_id)
        else:
            continue
        if sid:
            stix_to_sessions.setdefault(sid, []).append(s.id)

    if not stix_to_sessions:
        return []

    all_stix_ids = list(stix_to_sessions.keys())
    rels = StixRelationship.query.filter(
        StixRelationship.source_ref.in_(all_stix_ids),
        StixRelationship.relationship_type == "belongs-to",
    ).all()

    as_stix_ids = {r.target_ref for r in rels}
    as_map = {}
    if as_stix_ids:
        for a in StixAutonomousSystem.query.filter(StixAutonomousSystem.stix_id.in_(as_stix_ids)).all():
            # Include AS name from raw if available
            name = a.raw.get("name", "") if a.raw else ""
            label = f"AS{a.value}" + (f" ({name})" if name else "")
            as_map[a.stix_id] = label

    for r in rels:
        as_label = as_map.get(r.target_ref)
        if as_label:
            counter[as_label] += len(stix_to_sessions.get(r.source_ref, []))

    return [
        {"value": val, "count": cnt}
        for val, cnt in counter.most_common(limit)
    ]


def _aggregate_private_ip(session_ids, limit: int):
    """Group sessions by private vs public IP."""
    from models import Session
    sessions = Session.query.filter(Session.id.in_(session_ids)).all()
    private = 0
    public = 0
    for s in sessions:
        if _is_private_ip(s.client_ip):
            private += 1
        else:
            public += 1
    groups = []
    if private:
        groups.append({"value": "Private", "count": private})
    if public:
        groups.append({"value": "Public", "count": public})
    groups.sort(key=lambda g: g["count"], reverse=True)
    return groups[:limit]


# ── Handlers ──────────────────────────────────────────────────────────────────


def _handle_private_ip(query, op, value):
    """Filter sessions by private/public IP address."""
    from models import Session

    want_private = str(value).lower() in ("true", "1", "yes")
    # Flip for neq operator
    if op == "neq":
        want_private = not want_private

    sessions = query.all()
    matching_ids = [
        s.id for s in sessions
        if _is_private_ip(s.client_ip) == want_private
    ]
    if matching_ids:
        return Session.query.filter(Session.id.in_(matching_ids))
    return Session.query.filter(False)


def _is_private_ip(ip_str: str) -> bool:
    try:
        return ipaddress.ip_address(ip_str).is_private
    except (ValueError, TypeError):
        return False


def _handle_ip_as(query, op, value):
    """Filter sessions whose IP belongs to a specific Autonomous System."""
    from models import (
        Session, StixIPv4Addr, StixIPv6Addr,
        StixRelationship, StixAutonomousSystem,
    )

    as_obj = StixAutonomousSystem.query.filter_by(value=str(value)).first()
    if not as_obj:
        return query.filter(False)

    rels = StixRelationship.query.filter_by(
        target_ref=as_obj.stix_id,
        relationship_type="belongs-to",
    ).all()
    if not rels:
        return query.filter(False)

    ip_stix_ids = {r.source_ref for r in rels}
    cond = _ip_observable_condition(ip_stix_ids)
    if cond is None:
        return query.filter(False)

    if op == "neq":
        return query.filter(~cond)
    return query.filter(cond)


def _handle_ip_country(query, op, value):
    """Filter sessions whose IP is located in a specific country."""
    from models import (
        Session, StixIPv4Addr, StixIPv6Addr,
        StixRelationship, StixCountry,
    )

    country_obj = StixCountry.query.filter_by(value=value.upper()).first()
    if not country_obj:
        return query.filter(False)

    rels = StixRelationship.query.filter_by(
        target_ref=country_obj.stix_id,
        relationship_type="located-at",
    ).all()
    if not rels:
        return query.filter(False)

    ip_stix_ids = {r.source_ref for r in rels}
    cond = _ip_observable_condition(ip_stix_ids)
    if cond is None:
        return query.filter(False)

    if op == "neq":
        return query.filter(~cond)
    return query.filter(cond)


def _ip_observable_condition(ip_stix_ids: set):
    """
    Given a set of IP STIX IDs, build a SQLAlchemy condition matching
    sessions that link to any of them via ip_observable_id.
    """
    from models import Session, StixIPv4Addr, StixIPv6Addr

    ipv4_ids = [
        o.id for o in
        StixIPv4Addr.query.filter(StixIPv4Addr.stix_id.in_(ip_stix_ids)).all()
    ]
    ipv6_ids = [
        o.id for o in
        StixIPv6Addr.query.filter(StixIPv6Addr.stix_id.in_(ip_stix_ids)).all()
    ]

    parts = []
    if ipv4_ids:
        parts.append(and_(
            Session.ip_observable_id.in_(ipv4_ids),
            Session.ip_observable_type == "ipv4-addr",
        ))
    if ipv6_ids:
        parts.append(and_(
            Session.ip_observable_id.in_(ipv6_ids),
            Session.ip_observable_type == "ipv6-addr",
        ))

    if not parts:
        return None
    return or_(*parts)


# ── Register built-in custom filters ─────────────────────────────────────────

register_custom_filter(
    "private_ip", "Private IP", "boolean",
    _handle_private_ip,
    aggregate=_aggregate_private_ip,
)
register_custom_filter(
    "ip_as", "IP Autonomous System (AS)", "string",
    _handle_ip_as,
    suggest=_suggest_as,
    aggregate=_aggregate_ip_as,
)
register_custom_filter(
    "ip_country", "IP Country Code", "string",
    _handle_ip_country,
    suggest=_suggest_country,
    aggregate=_aggregate_ip_country,
)

"""IP/STIX custom filters and aggregates."""

import ipaddress
from sqlalchemy import and_, or_

from .registry import register_custom_filter
from .suggestions import suggest_as, suggest_country


def _is_private_ip(ip_str: str) -> bool:
    try:
        return ipaddress.ip_address(ip_str).is_private
    except (ValueError, TypeError):
        return False


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


def _aggregate_ip_country(session_ids, limit: int):
    """Group sessions by IP country via STIX relationships."""
    from collections import Counter
    from models import Session, StixIPv4Addr, StixIPv6Addr, StixRelationship, StixCountry

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
        StixRelationship.relationship_type == "located-at",
    ).all()

    country_stix_ids = {r.target_ref for r in rels}
    country_map = {}
    if country_stix_ids:
        for c in StixCountry.query.filter(StixCountry.stix_id.in_(country_stix_ids)).all():
            country_map[c.stix_id] = c.value

    for r in rels:
        country = country_map.get(r.target_ref)
        if country:
            counter[country] += len(stix_to_sessions.get(r.source_ref, []))

    return [{"value": val, "count": cnt} for val, cnt in counter.most_common(limit)]


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
            name = a.raw.get("name", "") if a.raw else ""
            label = f"AS{a.value}" + (f" ({name})" if name else "")
            as_map[a.stix_id] = label

    for r in rels:
        as_label = as_map.get(r.target_ref)
        if as_label:
            counter[as_label] += len(stix_to_sessions.get(r.source_ref, []))

    return [{"value": val, "count": cnt} for val, cnt in counter.most_common(limit)]


def _ip_observable_condition(ip_stix_ids: set):
    """Build a condition for sessions linked to any of the given IP STIX IDs."""
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


def _handle_private_ip(query, op, value):
    """Filter sessions by private/public IP address."""
    from models import Session

    want_private = str(value).lower() in ("true", "1", "yes")
    if op == "neq":
        want_private = not want_private

    sessions = query.all()
    matching_ids = [s.id for s in sessions if _is_private_ip(s.client_ip) == want_private]
    if matching_ids:
        return Session.query.filter(Session.id.in_(matching_ids))
    return Session.query.filter(False)


def _handle_ip_as(query, op, value):
    """Filter sessions whose IP belongs to a specific Autonomous System."""
    from models import StixRelationship, StixAutonomousSystem

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
    from models import StixRelationship, StixCountry

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


def register_filters():
    """Register built-in IP/STIX custom filters."""
    register_custom_filter(
        "private_ip", "Private IP", "boolean",
        _handle_private_ip,
        aggregate=_aggregate_private_ip,
    )
    register_custom_filter(
        "ip_as", "IP Autonomous System (AS)", "string",
        _handle_ip_as,
        suggest=suggest_as,
        aggregate=_aggregate_ip_as,
    )
    register_custom_filter(
        "ip_country", "IP Country Code", "string",
        _handle_ip_country,
        suggest=suggest_country,
        aggregate=_aggregate_ip_country,
    )

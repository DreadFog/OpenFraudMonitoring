"""
Helpers for getting-or-creating STIX 2.1 observables/SDOs in the database.

Uses the `stix2` library to build canonical STIX objects, then persists them
into per-type tables (see `models/stix.py`).

Phase 1 scope: only the two observables produced at ingestion time
(IP address and user-agent string).  Other types (autonomous-system, country,
indicator, malware, campaign, intrusion-set) and relationships will be
populated by external connectors in a later phase.
"""

import ipaddress
import json
import logging
import uuid
from typing import Any, Optional, Union

import stix2
from services.database import db
from models.stix import (
    StixIPv4Addr, StixIPv6Addr, StixUserAgent,
    StixCountry, StixAutonomousSystem, StixRelationship,
)

logger = logging.getLogger(__name__)

IPObservable = Union[StixIPv4Addr, StixIPv6Addr]

# OASIS STIX namespace for deterministic UUIDv5 generation,
# matching the approach used by OpenCTI (identifier.js).
# UUID is derived from canonicalized JSON of contributing fields.
OASIS_NAMESPACE = uuid.UUID("00abedb4-aa42-466c-9c01-fed23315a9b7")


def _canonical(data: dict) -> str:
    """RFC 8785-style JSON canonicalization (sorted keys, compact)."""
    return json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def _to_plain(obj: Any) -> dict:
    """Convert a stix2 object into a JSON-safe dict for JSONB storage."""
    return json.loads(obj.serialize())


def _detect_ip_version(ip: str) -> Optional[int]:
    """Return 4, 6, or None if the string is not a valid IP address."""
    try:
        return ipaddress.ip_address(ip).version
    except (ValueError, TypeError):
        return None


def get_or_create_ip(ip: str) -> Optional[IPObservable]:
    """
    Persist a STIX ipv4-addr or ipv6-addr observable, returning the row.
    Returns None if the input is not a valid IP address.
    """
    if not ip:
        return None
    version = _detect_ip_version(ip)
    if version is None:
        return None

    Model = StixIPv4Addr if version == 4 else StixIPv6Addr
    existing = Model.query.filter_by(value=ip).first()
    if existing:
        return existing

    sco = stix2.IPv4Address(value=ip) if version == 4 else stix2.IPv6Address(value=ip)
    obj = Model(stix_id=sco.id, value=ip, raw=_to_plain(sco))
    db.session.add(obj)
    db.session.flush()
    return obj


def get_or_create_user_agent(user_agent: str) -> Optional[StixUserAgent]:
    """
    Persist a STIX 2.1 user-agent observable.  Empty / sentinel values return None.

    Emit an OpenCTI-like user-agent shape using OFM custom fields.
    We keep deterministic UUIDv5 identifiers for stable deduplication.
    """
    if not user_agent:
        return None
    ua = str(user_agent).strip()
    if not ua or ua in {"unknown", "ERROR", "INIT", "NA", "SKIPPED"}:
        return None
    ua = ua[:2048]

    existing = StixUserAgent.query.filter_by(value=ua).first()
    if existing:
        return existing

    stix_id = f"user-agent--{uuid.uuid5(OASIS_NAMESPACE, _canonical({'value': ua}))}"
    raw = {
        "type": "user-agent",
        "spec_version": "2.1",
        "id": stix_id,
        "value": ua,
        # Mirror string for compatibility with tools expecting the SCO field name.
        "string": ua,
        "x_ofm_type": "User-Agent",
    }
    try:
        raw = dict(stix2.parse(raw, allow_custom=True))
    except Exception:
        logger.debug("Could not parse user-agent with stix2; storing raw OFM shape", exc_info=True)

    obj = StixUserAgent(stix_id=stix_id, value=ua, raw=raw)
    db.session.add(obj)
    db.session.flush()
    return obj


def get_or_create_country(country_iso: str, country_name: Optional[str] = None) -> Optional[StixCountry]:
    """
    Persist a STIX 2.1 location (country) SDO.  `value` = ISO country code.
    Returns None if country_iso is empty.
    """
    if not country_iso:
        return None
    code = str(country_iso).strip().upper()[:16]
    if not code:
        return None

    existing = StixCountry.query.filter_by(value=code).first()
    if existing:
        return existing

    name = (country_name or code).strip()
    stix_id = f"location--{uuid.uuid5(OASIS_NAMESPACE, _canonical({'name': name.lower(), 'x_ofm_location_type': 'Country'}))}"
    location = stix2.Location(
        id=stix_id,
        country=code,
        name=name,
        allow_custom=True,
        x_ofm_location_type="Country",
        x_ofm_type="Country",
    )
    raw = _to_plain(location)
    obj = StixCountry(stix_id=stix_id, value=code, raw=raw)
    db.session.add(obj)
    db.session.flush()
    return obj


def get_or_create_autonomous_system(asn: str, asn_org: Optional[str] = None) -> Optional[StixAutonomousSystem]:
    """
    Persist a STIX 2.1 autonomous-system SCO.  `value` = AS number string (e.g. "AS12322").
    Returns None if asn is empty.
    """
    if not asn:
        return None
    asn_str = str(asn).strip()[:64]
    if not asn_str:
        return None

    existing = StixAutonomousSystem.query.filter_by(value=asn_str).first()
    if existing:
        return existing

    # Extract numeric part for the STIX object ("AS12322" -> 12322)
    asn_number = int("".join(c for c in asn_str if c.isdigit()) or "0")
    as_obj = stix2.AutonomousSystem(number=asn_number, name=asn_org or asn_str)
    raw = _to_plain(as_obj)
    obj = StixAutonomousSystem(stix_id=as_obj.id, value=asn_str, raw=raw)
    db.session.add(obj)
    db.session.flush()
    return obj


def get_or_create_relationship(source_stix_id: str, relationship_type: str, target_stix_id: str) -> Optional[StixRelationship]:
    """
    Persist a STIX 2.1 relationship SRO between two STIX objects.
    Deduplicates on the (source, type, target) triple.
    """
    if not source_stix_id or not target_stix_id:
        return None

    existing = StixRelationship.query.filter_by(
        source_ref=source_stix_id,
        relationship_type=relationship_type,
        target_ref=target_stix_id,
    ).first()
    if existing:
        return existing

    stix_id = f"relationship--{uuid.uuid5(OASIS_NAMESPACE, _canonical({'relationship_type': relationship_type, 'source_ref': source_stix_id, 'target_ref': target_stix_id}))}"
    rel = stix2.Relationship(
        id=stix_id,
        relationship_type=relationship_type,
        source_ref=source_stix_id,
        target_ref=target_stix_id,
    )
    raw = _to_plain(rel)
    obj = StixRelationship(
        stix_id=stix_id,
        relationship_type=relationship_type,
        source_ref=source_stix_id,
        target_ref=target_stix_id,
        raw=raw,
    )
    db.session.add(obj)
    db.session.flush()
    return obj

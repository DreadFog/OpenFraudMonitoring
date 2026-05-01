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
import logging
import uuid
from typing import Optional, Union

import stix2
from services.database import db
from models.stix import (
    StixIPv4Addr, StixIPv6Addr, StixUserAgent,
    StixCountry, StixAutonomousSystem, StixRelationship,
)

logger = logging.getLogger(__name__)

IPObservable = Union[StixIPv4Addr, StixIPv6Addr]

# Deterministic namespace for UUIDv5 ids so identical values
# produce the same STIX id across runs (stable deduplication).
_UA_NAMESPACE = uuid.UUID("00abedb4-aa42-466c-9c01-fed23315a9b7")
_COUNTRY_NAMESPACE = uuid.UUID("7a3e4b2c-1d5f-4e8a-9c0b-2f6d8e7a1b3c")
_AS_NAMESPACE = uuid.UUID("b1c2d3e4-f5a6-4b7c-8d9e-0f1a2b3c4d5e")
_REL_NAMESPACE = uuid.UUID("c4d5e6f7-a8b9-4c0d-1e2f-3a4b5c6d7e8f")


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
    obj = Model(stix_id=sco.id, value=ip, raw=dict(sco))
    db.session.add(obj)
    db.session.flush()
    return obj


def get_or_create_user_agent(user_agent: str) -> Optional[StixUserAgent]:
    """
    Persist a STIX 2.1 user-agent observable.  Empty / sentinel values return None.

    The `user-agent` SCO is part of STIX 2.1.  The stix2 library may not
    expose a typed class for it depending on the version installed, so we
    build a plain dict with a deterministic UUIDv5 id derived from the
    value (stable across runs).
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

    stix_id = f"user-agent--{uuid.uuid5(_UA_NAMESPACE, ua)}"
    raw = {
        "type": "user-agent",
        "spec_version": "2.1",
        "id": stix_id,
        "string": ua,
    }
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

    stix_id = f"location--{uuid.uuid5(_COUNTRY_NAMESPACE, code)}"
    raw = {
        "type": "location",
        "spec_version": "2.1",
        "id": stix_id,
        "country": code,
        "name": country_name or code,
    }
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
    stix_id = f"autonomous-system--{uuid.uuid5(_AS_NAMESPACE, asn_str)}"
    raw = {
        "type": "autonomous-system",
        "spec_version": "2.1",
        "id": stix_id,
        "number": asn_number,
        "name": asn_org or asn_str,
    }
    obj = StixAutonomousSystem(stix_id=stix_id, value=asn_str, raw=raw)
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

    key = f"{source_stix_id}|{relationship_type}|{target_stix_id}"
    stix_id = f"relationship--{uuid.uuid5(_REL_NAMESPACE, key)}"
    raw = {
        "type": "relationship",
        "spec_version": "2.1",
        "id": stix_id,
        "relationship_type": relationship_type,
        "source_ref": source_stix_id,
        "target_ref": target_stix_id,
    }
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

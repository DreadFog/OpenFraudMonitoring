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
from models.stix import StixIPv4Addr, StixIPv6Addr, StixUserAgent

logger = logging.getLogger(__name__)

IPObservable = Union[StixIPv4Addr, StixIPv6Addr]

# Deterministic namespace for user-agent UUIDv5 ids so identical strings
# produce the same STIX id across runs (stable deduplication).
_UA_NAMESPACE = uuid.UUID("00abedb4-aa42-466c-9c01-fed23315a9b7")


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

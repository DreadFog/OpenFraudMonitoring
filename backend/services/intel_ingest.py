"""
Persist a STIX bundle (returned by an intel connector) into the per-type
STIX tables.

Supported object types:
  ipv4-addr, ipv6-addr, user-agent, autonomous-system, location (country),
  indicator, malware, campaign, intrusion-set, relationship.

Unknown types are stored verbatim into a ``raw`` log but otherwise ignored
for now.

Sample created bundle based on the IPInfo connector
{'type': 'bundle', 'id': 'bundle--f2286958-57eb-4f30-acbf-5005f1487fdf', 
'objects': [
{'type': 'ipv6-addr', 'spec_version': '2.1', 'id': 'ipv6-addr--3d1bcfd3-3764-58c9-b283-6a69fe0f0277', 'value': '2a0d:e487:6ce:b5ee::1698:3d47'},
{'type': 'autonomous-system', 'spec_version': '2.1', 'id': 'autonomous-system--7b30ccf1-3f7f-53c4-bd3f-18877f6aef99', 'number': 51207, 'name': 'Free Mobile SAS'},
{'type': 'relationship', 'spec_version': '2.1', 'id': 'relationship--b029dbe4-1788-57f7-b36c-0f49453c6bc0', 'relationship_type': 'belongs-to', 'source_ref': 'ipv6-addr--3d1bcfd3-3764-58c9-b283-6a69fe0f0277', 'target_ref': 'autonomous-system--7b30ccf1-3f7f-53c4-bd3f-18877f6aef99'},
{'type': 'location', 'spec_version': '2.1', 'id': 'location--597ce4b1-a421-517c-b703-9e20d586d79c', 'name': 'France', 'country': 'FR'},
{'type': 'relationship', 'spec_version': '2.1', 'id': 'relationship--18ea03c9-b3e3-539a-8ed0-942eb06d12f9', 'relationship_type': 'located-at', 'source_ref': 'ipv6-addr--3d1bcfd3-3764-58c9-b283-6a69fe0f0277', 'target_ref': 'location--597ce4b1-a421-517c-b703-9e20d586d79c'}
]}'

"""

import logging
from datetime import datetime
from typing import Optional

from services.database import db
from models import (
    StixIPv4Addr,
    StixIPv6Addr,
    StixUserAgent,
    StixAutonomousSystem,
    StixCountry,
    StixIndicator,
    StixMalware,
    StixCampaign,
    StixIntrusionSet,
    StixRelationship,
)

logger = logging.getLogger(__name__)


# Map STIX object type -> (Model, function(obj) -> value string)
_TYPE_MAP = {
    "ipv4-addr":         (StixIPv4Addr,        lambda o: o.get("value", "")),
    "ipv6-addr":         (StixIPv6Addr,        lambda o: o.get("value", "")),
    "user-agent":        (StixUserAgent,       lambda o: o.get("string", "")),
    "autonomous-system": (StixAutonomousSystem, lambda o: str(o.get("number", ""))),
    "indicator":         (StixIndicator,       lambda o: o.get("pattern", "")[:2048]),
    "malware":           (StixMalware,         lambda o: o.get("name", "")),
    "campaign":          (StixCampaign,        lambda o: o.get("name", "")),
    "intrusion-set":     (StixIntrusionSet,    lambda o: o.get("name", "")),
}


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _upsert_typed(obj: dict, source_connector_id: int = None) -> None:
    logging.debug("Adding object: '%s'", obj)
    otype = obj.get("type")
    sid = obj.get("id")
    if not sid:
        return

    if otype == "location":
        # Only treat as Country if a country code is present.
        country = obj.get("country")
        if not country:
            return
        Model = StixCountry
        value = country
    else:
        entry = _TYPE_MAP.get(otype)
        if not entry:
            return
        Model, value_fn = entry
        value = value_fn(obj) or ""

    existing = Model.query.filter_by(stix_id=sid).first()
    if existing:
        logging.debug("Object exists in database: '%s'", existing)
        existing.raw = obj
        existing.last_refreshed_at = datetime.utcnow()
        existing.decayed = False
        if value:
            existing.value = value[:2048]
        if source_connector_id is not None:
            existing.source_connector_id = source_connector_id
    else:
        logging.debug("Object did not exist in the database. Adding...")
        db.session.add(Model(
            stix_id=sid,
            value=(value or sid)[:2048],
            raw=obj,
            last_refreshed_at=datetime.utcnow(),
            source_connector_id=source_connector_id,
        ))


def _upsert_relationship(obj: dict, source_connector_id: int = None) -> None:
    logging.debug("Adding relationship: '%s'", obj)
    sid = obj.get("id")
    if not sid:
        return
    existing = StixRelationship.query.filter_by(stix_id=sid).first()
    if existing:
        logging.debug("Relationship exists in database: '%s'", existing)
        existing.raw = obj
        existing.relationship_type = obj.get("relationship_type", existing.relationship_type)
        existing.source_ref = obj.get("source_ref", existing.source_ref)
        existing.target_ref = obj.get("target_ref", existing.target_ref)
        existing.start_time = _parse_iso(obj.get("start_time")) or existing.start_time
        existing.stop_time = _parse_iso(obj.get("stop_time")) or existing.stop_time
        existing.decayed = False
        if source_connector_id is not None:
            existing.source_connector_id = source_connector_id
    else:
        logging.debug("Relationship did not exist in the database. Adding...")
        db.session.add(StixRelationship(
            stix_id=sid,
            relationship_type=obj.get("relationship_type", ""),
            source_ref=obj.get("source_ref", ""),
            target_ref=obj.get("target_ref", ""),
            start_time=_parse_iso(obj.get("start_time")),
            stop_time=_parse_iso(obj.get("stop_time")),
            raw=obj,
            source_connector_id=source_connector_id,
        ))


def ingest_bundle(bundle: dict, source_connector_id: int = None) -> int:
    """
    Persist all objects from a STIX 2.1 bundle.  Returns the number of
    objects written/updated.
    """
    if not isinstance(bundle, dict):
        return 0
    objects = bundle.get("objects") or []
    count = 0
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        try:
            if obj.get("type") == "relationship":
                _upsert_relationship(obj, source_connector_id=source_connector_id)
            else:
                _upsert_typed(obj, source_connector_id=source_connector_id)
            count += 1
        except Exception as e:
            logger.exception("Failed to ingest STIX object %s: %s", obj.get("id"), e)
    db.session.commit()
    return count

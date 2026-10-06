"""
OpenCTI client for the OFM intel connector.

Uses the official `pycti` client.  Given an IP address (v4 or v6) we:

1. Look up the observable on OpenCTI (StixCyberObservable).
2. Pull all "based-on" indicators referencing it.
3. For each indicator, pull its "indicates" relationships pointing at
   malware / campaign / intrusion-set SDOs.
4. Pull "belongs-to" relationships from the IP to autonomous-system observables.
5. Pull "located-at" relationships from the IP to country location SDOs.

Returned object is a STIX 2.1 bundle dict that the backend can ingest.
"""

import ipaddress
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pycti import OpenCTIApiClient

logger = logging.getLogger(__name__)


# Relationship types this connector cares about.
_INTEREST_RELATIONSHIPS = {"based-on", "indicates", "belongs-to", "located-at"}
# SDO types that can be the target of an "indicates" relationship.
_INDICATES_TARGETS = {"Malware", "Campaign", "Intrusion-Set"}
_INDICATOR_ATTRIBUTES = """
    id
    standard_id
    entity_type
    parent_types
    spec_version
    created_at
    updated_at
    objectLabel {
        value
    }
    ... on StixDomainObject {
        created
        modified
        revoked
        confidence
    }
    ... on Indicator {
        name
        description
        pattern
        pattern_type
        pattern_version
        valid_from
        valid_until
        indicator_types
        x_opencti_score
        x_opencti_detection
        x_opencti_main_observable_type
    }
"""
_COMMON_OBJECT_FIELDS = {
    "created_by_ref", "created", "modified", "revoked", "labels", "confidence",
    "lang", "external_references", "object_marking_refs", "granular_markings",
    "defanged", "extensions",
}
_TYPE_OBJECT_FIELDS = {
    "ipv4-addr": {"value", "resolves_to_refs", "belongs_to_refs"},
    "ipv6-addr": {"value", "resolves_to_refs", "belongs_to_refs"},
    "autonomous-system": {"number", "name", "rir"},
    "user-agent": {"value"},
    "location": {
        "name", "description", "latitude", "longitude", "precision", "region",
        "country", "administrative_area", "city", "street_address", "postal_code",
    },
    "indicator": {
        "name", "description", "indicator_types", "pattern", "pattern_type",
        "pattern_version", "valid_from", "valid_until", "kill_chain_phases",
    },
    "malware": {
        "name", "description", "malware_types", "is_family", "aliases",
        "kill_chain_phases", "first_seen", "last_seen", "operating_system_refs",
        "architecture_execution_envs", "implementation_languages", "capabilities",
        "sample_refs",
    },
    "campaign": {"name", "description", "aliases", "first_seen", "last_seen", "objective"},
    "intrusion-set": {
        "name", "description", "aliases", "first_seen", "last_seen", "goals",
        "resource_level", "primary_motivation", "secondary_motivations",
    },
    "relationship": {
        "relationship_type", "description", "source_ref", "target_ref", "start_time", "stop_time",
    },
}


def _detect_ip_type(ip: str) -> Optional[str]:
    try:
        v = ipaddress.ip_address(ip).version
        return "IPv4-Addr" if v == 4 else "IPv6-Addr"
    except (ValueError, TypeError):
        return None


class OpenCTIClient:
    def __init__(self, url: str, token: str, ssl_verify: bool = True):
        self.url = url
        # pycti expects URL with scheme
        if not url.startswith(("http://", "https://")):
            self.url = f"https://{url}"
        self.client = OpenCTIApiClient(self.url, token, ssl_verify=ssl_verify)

    # ── Public API ──

    def lookup_ip(self, ip: str) -> Dict[str, Any]:
        """Return a STIX 2.1 bundle for an IP and all related intel."""
        ip_type = _detect_ip_type(ip)
        objects: List[Dict[str, Any]] = []
        seen_ids: set = set()

        if ip_type is None:
            return _empty_bundle()

        observable = self._fetch_observable(ip, ip_type)
        if not observable:
            logger.info("OpenCTI: no observable found for %s", ip)
            return _empty_bundle()

        ip_stix = _observable_to_stix(observable)
        _add(objects, seen_ids, ip_stix)
        ip_stix_id = ip_stix["id"]
        ip_octi_id = observable["id"]  # internal opencti id, used for queries

        # Discover indicators explicitly through based-on relationships targeting this IP.
        based_on_rels = self._fetch_relationships(
            ip_octi_id,
            relationship_type="based-on",
            direction="to",
            from_types=["Indicator"],
        )
        for rel in based_on_rels:
            indicator_summary = rel.get("from") or {}
            if not indicator_summary or indicator_summary.get("entity_type") != "Indicator":
                continue
            indicator = self._fetch_indicator(indicator_summary)
            if indicator is None:
                continue
            ind_stix = _indicator_to_stix(indicator)
            if not _add(objects, seen_ids, ind_stix):
                continue
            _add(objects, seen_ids, _relationship_to_stix(
                rel, source_id=ind_stix["id"], target_id=ip_stix_id,
            ))

            # ── 2. indicator indicates malware/campaign/intrusion-set ──
            for ind_rel in self._fetch_relationships(
                indicator["id"],
                relationship_type="indicates",
                direction="from",
                to_types=sorted(_INDICATES_TARGETS),
            ):
                target = ind_rel.get("to") or {}
                etype = target.get("entity_type")
                if etype not in _INDICATES_TARGETS:
                    continue
                tgt_stix = _sdo_to_stix(target)
                if not _add(objects, seen_ids, tgt_stix):
                    continue
                _add(objects, seen_ids, _relationship_to_stix(
                    ind_rel, source_id=ind_stix["id"], target_id=tgt_stix["id"],
                ))

        # Fetch standard enrichment relationships originating from this IP.
        rels = self._fetch_relationships(ip_octi_id, direction="from")

        # ── 3. IP belongs-to AS ──
        belongs_to_rels = [r for r in rels if r.get("relationship_type") == "belongs-to"]
        for rel in belongs_to_rels:
            target = rel.get("to") or {}
            if target.get("entity_type") != "Autonomous-System":
                continue
            as_stix = _autonomous_system_to_stix(target)
            if not _add(objects, seen_ids, as_stix):
                continue
            _add(objects, seen_ids, _relationship_to_stix(
                rel, source_id=ip_stix_id, target_id=as_stix["id"],
            ))

        # ── 4. IP located-at country ──
        located_rels = [r for r in rels if r.get("relationship_type") == "located-at"]
        for rel in located_rels:
            target = rel.get("to") or {}
            if target.get("entity_type") not in {"Country", "Location"}:
                continue
            loc_stix = _country_to_stix(target)
            if not _add(objects, seen_ids, loc_stix):
                continue
            _add(objects, seen_ids, _relationship_to_stix(
                rel, source_id=ip_stix_id, target_id=loc_stix["id"],
            ))

        return {
            "type": "bundle",
            "id": f"bundle--{uuid.uuid4()}",
            "objects": objects,
        }

    # ── Internal queries ──

    def _fetch_observable(self, value: str, ip_type: str) -> Optional[Dict[str, Any]]:
        try:
            obs = self.client.stix_cyber_observable.list(
                types=[ip_type],
                filters={
                    "mode": "and",
                    "filters": [{"key": "value", "values": [value]}],
                    "filterGroups": [],
                },
                first=1,
            )
            return obs[0] if obs else None
        except Exception as e:
            logger.exception("OpenCTI observable lookup failed: %s", e)
            return None

    def _fetch_relationships(
        self,
        internal_id: str,
        relationship_type: Optional[str] = None,
        direction: str = "both",
        from_types: Optional[List[str]] = None,
        to_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        if direction not in {"from", "to", "both"}:
            raise ValueError("relationship direction must be from, to, or both")

        query = {"first": 200, "getAll": True}
        if relationship_type:
            query["relationship_type"] = relationship_type
        if from_types:
            query["fromTypes"] = from_types
        if to_types:
            query["toTypes"] = to_types
        directions = ("from", "to") if direction == "both" else (direction,)
        for side in directions:
            try:
                results.extend(self.client.stix_core_relationship.list(
                    **query,
                    **{"fromId" if side == "from" else "toId": internal_id},
                ) or [])
            except Exception as e:
                logger.debug("rel list %sId=%s failed: %s", side, internal_id, e)
        # Dedup by relationship id
        seen = set()
        unique: List[Dict[str, Any]] = []
        for r in results:
            rid = r.get("id")
            if rid and rid not in seen:
                seen.add(rid)
                unique.append(r)
        return unique

    def _fetch_indicator(self, summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Read the complete Indicator so revoked state and STIX pattern fields are available."""
        indicator_id = summary.get("id")
        if not indicator_id:
            return None
        try:
            indicator = self.client.stix_core_object.read(
                id=indicator_id,
                customAttributes=_INDICATOR_ATTRIBUTES,
            )
        except Exception:
            logger.exception("OpenCTI Indicator read failed for %s", indicator_id)
            return None
        if not isinstance(indicator, dict) or indicator.get("entity_type") != "Indicator":
            return None
        if indicator.get("revoked") is True:
            logger.info("Skipping revoked Indicator %s", indicator_id)
            return None
        return indicator


# ── STIX builders (return plain dicts ready for the backend bundle) ───────

def _empty_bundle() -> Dict[str, Any]:
    return {"type": "bundle", "id": f"bundle--{uuid.uuid4()}", "objects": []}


def _add(objects: List[Dict[str, Any]], seen: set, obj: Optional[Dict[str, Any]]) -> bool:
    """Append obj if its id is new.  Returns True if appended."""
    if not obj or not obj.get("id"):
        return False
    if obj["id"] in seen:
        return False
    seen.add(obj["id"])
    objects.append(obj)
    return True


def _stix_id(prefix: str, octi_obj: Dict[str, Any]) -> str:
    """Use the OpenCTI standard_id when present, else synthesize one."""
    sid = octi_obj.get("standard_id")
    if sid:
        return sid
    return f"{prefix}--{octi_obj.get('id') or uuid.uuid4()}"


def _observable_to_stix(o: Dict[str, Any]) -> Dict[str, Any]:
    etype = o.get("entity_type", "")
    if etype == "IPv4-Addr":
        prefix, stype = "ipv4-addr", "ipv4-addr"
    elif etype == "IPv6-Addr":
        prefix, stype = "ipv6-addr", "ipv6-addr"
    else:
        prefix, stype = etype.lower(), etype.lower()
    return _opencti_fields({
        "type": stype,
        "spec_version": "2.1",
        "id": _stix_id(prefix, o),
        "value": o.get("observable_value") or o.get("value"),
    }, o, stype)


def _indicator_to_stix(o: Dict[str, Any]) -> Dict[str, Any]:
    if not o.get("pattern"):
        return None
    labels = o.get("labels")
    if labels is None:
        labels = o.get("objectLabel") or []
    if isinstance(labels, str):
        labels = [labels]
    elif isinstance(labels, dict):
        labels = labels.get("edges") or labels.get("values") or []
        labels = [item.get("node", item) if isinstance(item, dict) else item for item in labels]
    labels = [
        label.get("value") if isinstance(label, dict) else label
        for label in labels
        if isinstance(label, (str, dict))
    ]
    labels = list(dict.fromkeys(label for label in labels if isinstance(label, str) and label))
    return _opencti_fields({
        "type": "indicator",
        "spec_version": "2.1",
        "id": _stix_id("indicator", o),
        "name": o.get("name"),
        "pattern": o.get("pattern"),
        "pattern_type": o.get("pattern_type", "stix"),
        "valid_from": o.get("valid_from"),
        "valid_until": o.get("valid_until"),
        "labels": labels or None,
    }, o, "indicator")


def _sdo_to_stix(o: Dict[str, Any]) -> Dict[str, Any]:
    etype = (o.get("entity_type") or "").lower()
    if etype in {"malware", "campaign", "intrusion-set"} and not o.get("name"):
        return None
    payload = {
        "type": etype,
        "spec_version": "2.1",
        "id": _stix_id(etype, o),
        "name": o.get("name"),
        "description": o.get("description"),
    }
    if etype == "malware":
        payload["is_family"] = o.get("is_family", False)
        payload["malware_types"] = o.get("malware_types")
    if etype in {"campaign", "intrusion-set"}:
        payload["aliases"] = o.get("aliases")
    return _opencti_fields(payload, o, etype)


def _autonomous_system_to_stix(o: Dict[str, Any]) -> Dict[str, Any]:
    return _opencti_fields({
        "type": "autonomous-system",
        "spec_version": "2.1",
        "id": _stix_id("autonomous-system", o),
        "number": o.get("number"),
        "name": o.get("name"),
    }, o, "autonomous-system")


def _country_to_stix(o: Dict[str, Any]) -> Dict[str, Any]:
    aliases = o.get("x_opencti_aliases") or []
    country = o.get("country") or o.get("name")
    return _opencti_fields({
        "type": "location",
        "spec_version": "2.1",
        "id": _stix_id("location", o),
        "name": o.get("name"),
        "country": country,
        "latitude": o.get("latitude"),
        "longitude": o.get("longitude"),
        "x_opencti_aliases": aliases or None,
        "x_opencti_location_type": "Country",
    }, o, "location")


def _relationship_to_stix(rel: Dict[str, Any], source_id: str, target_id: str) -> Dict[str, Any]:
    return _opencti_fields({
        "type": "relationship",
        "spec_version": "2.1",
        "id": _stix_id("relationship", rel),
        "relationship_type": rel.get("relationship_type"),
        "source_ref": source_id,
        "target_ref": target_id,
        "start_time": rel.get("start_time"),
        "stop_time": rel.get("stop_time"),
    }, rel, "relationship")


def _opencti_fields(payload: Dict[str, Any], source: Dict[str, Any], stix_type: str) -> Dict[str, Any]:
    payload = {key: value for key, value in payload.items() if value is not None}
    passthrough = _COMMON_OBJECT_FIELDS | _TYPE_OBJECT_FIELDS.get(stix_type, set())
    for key, value in source.items():
        if (
            (key in passthrough or key.startswith("x_opencti_"))
            and key not in {"id", "type", "spec_version", "created_at", "updated_at"}
            and key not in payload
        ):
            payload[key] = value
    opencti_type = {
        "ipv4-addr": "IPv4-Addr",
        "ipv6-addr": "IPv6-Addr",
        "autonomous-system": "Autonomous-System",
        "user-agent": "User-Agent",
        "location": "Country",
        "indicator": "Indicator",
        "malware": "Malware",
        "campaign": "Campaign",
        "intrusion-set": "Intrusion-Set",
        "relationship": source.get("relationship_type", "relationship"),
    }.get(stix_type, stix_type)
    payload["x_opencti_id"] = source.get("x_opencti_id") or source.get("id") or str(uuid.uuid4())
    payload["x_opencti_type"] = opencti_type
    payload["x_opencti_score"] = source.get("x_opencti_score") if source.get("x_opencti_score") is not None else 50

    if stix_type in {"location", "indicator", "malware", "campaign", "intrusion-set", "relationship"}:
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        created = source.get("created") or source.get("created_at") or now
        modified = source.get("modified") or source.get("updated_at") or created
        payload["created"] = created
        payload["modified"] = modified
        payload["revoked"] = source.get("revoked") if source.get("revoked") is not None else False
        payload["confidence"] = source.get("confidence") if source.get("confidence") is not None else 100
        if stix_type == "indicator":
            if not payload.get("pattern_type"):
                payload["pattern_type"] = "stix"
            if not payload.get("valid_from"):
                payload["valid_from"] = created
        elif stix_type == "malware" and payload.get("is_family") is None:
            payload["is_family"] = False
    if stix_type == "relationship":
        payload["lang"] = source.get("lang", "en")
    return {key: value for key, value in payload.items() if value is not None}

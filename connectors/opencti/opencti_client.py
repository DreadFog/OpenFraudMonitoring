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
from typing import Any, Dict, List, Optional

from pycti import OpenCTIApiClient

logger = logging.getLogger(__name__)


# Relationship types this connector cares about.
_INTEREST_RELATIONSHIPS = {"based-on", "indicates", "belongs-to", "located-at"}
# SDO types that can be the target of an "indicates" relationship.
_INDICATES_TARGETS = {"Malware", "Campaign", "Intrusion-Set"}


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

        # Fetch all relationships from/to this observable
        rels = self._fetch_relationships(ip_octi_id)

        # ── 1. based-on  (indicator) ──
        based_on_rels = [r for r in rels if r.get("relationship_type") == "based-on" and r.get("toId") == ip_octi_id]
        for rel in based_on_rels:
            indicator = rel.get("from") or {}
            if not indicator or indicator.get("entity_type") != "Indicator":
                continue
            ind_stix = _indicator_to_stix(indicator)
            if not _add(objects, seen_ids, ind_stix):
                continue
            _add(objects, seen_ids, _relationship_to_stix(
                rel, source_id=ind_stix["id"], target_id=ip_stix_id,
            ))

            # ── 2. indicator indicates malware/campaign/intrusion-set ──
            for ind_rel in self._fetch_relationships(indicator["id"]):
                if ind_rel.get("relationship_type") != "indicates":
                    continue
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

        # ── 3. IP belongs-to AS ──
        belongs_to_rels = [r for r in rels if r.get("relationship_type") == "belongs-to" and r.get("fromId") == ip_octi_id]
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
        located_rels = [r for r in rels if r.get("relationship_type") == "located-at" and r.get("fromId") == ip_octi_id]
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

    def _fetch_relationships(self, opencti_internal_id: str) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        try:
            results.extend(self.client.stix_core_relationship.list(
                fromId=opencti_internal_id, first=200,
            ) or [])
        except Exception as e:
            logger.debug("rel list fromId=%s failed: %s", opencti_internal_id, e)
        try:
            results.extend(self.client.stix_core_relationship.list(
                toId=opencti_internal_id, first=200,
            ) or [])
        except Exception as e:
            logger.debug("rel list toId=%s failed: %s", opencti_internal_id, e)
        # Dedup by relationship id
        seen = set()
        unique: List[Dict[str, Any]] = []
        for r in results:
            rid = r.get("id")
            if rid and rid not in seen:
                seen.add(rid)
                unique.append(r)
        return unique


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
    return {
        "type": stype,
        "spec_version": "2.1",
        "id": _stix_id(prefix, o),
        "value": o.get("observable_value") or o.get("value"),
        "_octi_created_at": o.get("created_at"),
    }


def _indicator_to_stix(o: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "indicator",
        "spec_version": "2.1",
        "id": _stix_id("indicator", o),
        "name": o.get("name"),
        "pattern": o.get("pattern"),
        "pattern_type": o.get("pattern_type", "stix"),
        "valid_from": o.get("valid_from"),
        "valid_until": o.get("valid_until"),
        "confidence": o.get("confidence"),
        "_octi_created_at": o.get("created_at"),
    }


def _sdo_to_stix(o: Dict[str, Any]) -> Dict[str, Any]:
    etype = (o.get("entity_type") or "").lower()
    return {
        "type": etype,
        "spec_version": "2.1",
        "id": _stix_id(etype, o),
        "name": o.get("name"),
        "description": o.get("description"),
        "_octi_created_at": o.get("created_at"),
    }


def _autonomous_system_to_stix(o: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "autonomous-system",
        "spec_version": "2.1",
        "id": _stix_id("autonomous-system", o),
        "number": o.get("number"),
        "name": o.get("name"),
        "_octi_created_at": o.get("created_at"),
    }


def _country_to_stix(o: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "location",
        "spec_version": "2.1",
        "id": _stix_id("location", o),
        "name": o.get("name"),
        "country": o.get("x_opencti_aliases", [None])[0] if o.get("x_opencti_aliases") else (o.get("name") or "")[:2],
        "_octi_created_at": o.get("created_at"),
    }


def _relationship_to_stix(rel: Dict[str, Any], source_id: str, target_id: str) -> Dict[str, Any]:
    return {
        "type": "relationship",
        "spec_version": "2.1",
        "id": _stix_id("relationship", rel),
        "relationship_type": rel.get("relationship_type"),
        "source_ref": source_id,
        "target_ref": target_id,
        "start_time": rel.get("start_time"),
        "stop_time": rel.get("stop_time"),
        "_octi_created_at": rel.get("created_at"),
    }

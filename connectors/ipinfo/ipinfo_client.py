"""
IPinfo client for the OFM intel connector.

Given an IP address (v4 or v6), queries the IPinfo Lite API and returns
a STIX 2.1 bundle containing:
  - the IP observable (ipv4-addr or ipv6-addr)
  - an autonomous-system SCO (if ASN data is present)
  - a location SDO / country (if country data is present)
  - relationship SROs linking them:
      IP  --belongs-to-->  autonomous-system
      IP  --located-at-->  location (country)
"""

import ipaddress
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests
import stix2

logger = logging.getLogger(__name__)

# OASIS STIX namespace for deterministic UUIDv5 generation.
_OASIS_NAMESPACE = uuid.UUID("00abedb4-aa42-466c-9c01-fed23315a9b7")
_OFM_SDO_SRO_NAMESPACE = uuid.UUID("6b28b8d1-91e4-4cdf-b5e6-2a7fc033f6d1")


def _canonical(data: dict) -> str:
    """RFC 8785-style JSON canonicalization (sorted keys, compact)."""
    return json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def _detect_ip_type(ip: str) -> Optional[str]:
    try:
        v = ipaddress.ip_address(ip).version
        return "ipv4-addr" if v == 4 else "ipv6-addr"
    except (ValueError, TypeError):
        return None


def _make_rel_id(source_id: str, rel_type: str, target_id: str) -> str:
    return f"relationship--{uuid.uuid5(_OFM_SDO_SRO_NAMESPACE, _canonical({'relationship_type': rel_type, 'source_ref': source_id, 'target_ref': target_id}))}"


def _to_plain(obj) -> Dict[str, Any]:
    """Convert a stix2 object into a JSON-safe dict (no STIXdatetime instances)."""
    return json.loads(obj.serialize())


def _interop_object(obj, external_type: str, external_id: str, score: int = 50) -> Dict[str, Any]:
    payload = _to_plain(obj)
    payload.update({
        "x_opencti_id": external_id,
        "x_opencti_type": external_type,
        "x_opencti_score": score,
    })
    if payload.get("type") in {"location", "indicator", "malware", "campaign", "intrusion-set", "relationship"}:
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        payload.setdefault("created", now)
        payload.setdefault("modified", payload["created"])
        payload.setdefault("revoked", False)
        payload.setdefault("confidence", 100)
    if payload.get("type") == "relationship":
        payload.setdefault("lang", "en")
    return payload


class IPInfoClient:
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.ipinfo.io/lite"

    def lookup_ip(self, ip: str) -> Dict[str, Any]:
        """Query IPinfo Lite and return a STIX 2.1 bundle."""
        ip_type = _detect_ip_type(ip)
        if ip_type is None:
            return _empty_bundle()

        try:
            r = requests.get(
                f"{self.base_url}/{ip}",
                params={"token": self.token},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            logger.debug("IPinfo returned the following data: '%s'", str(data))
        except Exception as e:
            logger.warning("IPinfo lookup failed for %s: %s", ip, e)
            return _empty_bundle()

        objects = []
        seen = set()

        # 1. IP observable
        ip_obj = stix2.IPv4Address(value=ip) if ip_type == "ipv4-addr" else stix2.IPv6Address(value=ip)
        ip_stix_id = ip_obj.id
        ip_stix = _interop_object(
            ip_obj,
            "IPv4-Addr" if ip_type == "ipv4-addr" else "IPv6-Addr",
            str(uuid.uuid5(_OASIS_NAMESPACE, f"ipinfo:{ip_obj.id}")),
        )
        _add(objects, seen, ip_stix)

        # 2. Autonomous System
        asn_raw = data.get("asn")  # e.g. "AS15169"
        as_name = data.get("as_name")  # e.g. "Google LLC"
        if asn_raw:
            asn_number = int("".join(c for c in asn_raw if c.isdigit()) or "0")
            as_obj = stix2.AutonomousSystem(number=asn_number, name=as_name or asn_raw)
            as_stix_id = as_obj.id
            _add(objects, seen, _interop_object(
                as_obj,
                "Autonomous-System",
                str(uuid.uuid5(_OASIS_NAMESPACE, f"ipinfo:{as_obj.id}")),
            ))

            # IP belongs-to AS
            rel_id = _make_rel_id(ip_stix_id, "belongs-to", as_stix_id)
            rel = stix2.Relationship(
                id=rel_id,
                relationship_type="belongs-to",
                source_ref=ip_stix_id,
                target_ref=as_stix_id,
            )
            _add(objects, seen, _interop_object(
                rel, "belongs-to", str(uuid.uuid5(_OASIS_NAMESPACE, f"ipinfo:{rel_id}")),
            ))

        # 3. Country
        country_code = data.get("country_code")  # e.g. "US"
        country_name = data.get("country")  # e.g. "United States"
        if country_code:
            country_name = (country_name or country_code).strip()
            country_stix_id = f"location--{uuid.uuid5(_OFM_SDO_SRO_NAMESPACE, _canonical({'country_code': country_code.upper()}))}"
            coordinates = {}
            try:
                if data.get("latitude") is not None and data.get("longitude") is not None:
                    coordinates = {
                        "latitude": float(data["latitude"]),
                        "longitude": float(data["longitude"]),
                    }
            except (TypeError, ValueError):
                coordinates = {}
            country_obj = stix2.Location(
                id=country_stix_id,
                name=country_name or country_code,
                country=country_name or country_code,
                revoked=False,
                confidence=100,
                allow_custom=True,
                x_opencti_aliases=[country_code.upper()],
                x_opencti_location_type="Country",
                x_opencti_type="Country",
                **coordinates,
            )
            _add(objects, seen, _interop_object(
                country_obj,
                "Country",
                str(uuid.uuid5(_OASIS_NAMESPACE, f"ipinfo:{country_stix_id}")),
            ))

            # IP located-at country
            rel_id = _make_rel_id(ip_stix_id, "located-at", country_stix_id)
            rel = stix2.Relationship(
                id=rel_id,
                relationship_type="located-at",
                source_ref=ip_stix_id,
                target_ref=country_stix_id,
            )
            _add(objects, seen, _interop_object(
                rel, "located-at", str(uuid.uuid5(_OASIS_NAMESPACE, f"ipinfo:{rel_id}")),
            ))

        return {
            "type": "bundle",
            "id": f"bundle--{uuid.uuid4()}",
            "objects": objects,
        }


def _empty_bundle() -> Dict[str, Any]:
    return {"type": "bundle", "id": f"bundle--{uuid.uuid4()}", "objects": []}


def _add(objects, seen, obj):
    if not obj or not obj.get("id"):
        return False
    if obj["id"] in seen:
        return False
    seen.add(obj["id"])
    objects.append(obj)
    return True

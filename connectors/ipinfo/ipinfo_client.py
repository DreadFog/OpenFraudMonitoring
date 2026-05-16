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
from typing import Any, Dict, Optional

import requests
import stix2

logger = logging.getLogger(__name__)

# OASIS STIX namespace for deterministic UUIDv5 generation,
# matching the approach used by OpenCTI (identifier.js).
_OASIS_NAMESPACE = uuid.UUID("00abedb4-aa42-466c-9c01-fed23315a9b7")


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
    return f"relationship--{uuid.uuid5(_OASIS_NAMESPACE, _canonical({'relationship_type': rel_type, 'source_ref': source_id, 'target_ref': target_id}))}"


def _to_plain(obj) -> Dict[str, Any]:
    """Convert a stix2 object into a JSON-safe dict (no STIXdatetime instances)."""
    return json.loads(obj.serialize())


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
        _add(objects, seen, _to_plain(ip_obj))

        # 2. Autonomous System
        asn_raw = data.get("asn")  # e.g. "AS15169"
        as_name = data.get("as_name")  # e.g. "Google LLC"
        if asn_raw:
            asn_number = int("".join(c for c in asn_raw if c.isdigit()) or "0")
            as_obj = stix2.AutonomousSystem(number=asn_number, name=as_name or asn_raw)
            as_stix_id = as_obj.id
            _add(objects, seen, _to_plain(as_obj))

            # IP belongs-to AS
            rel_id = _make_rel_id(ip_stix_id, "belongs-to", as_stix_id)
            rel = stix2.Relationship(
                id=rel_id,
                relationship_type="belongs-to",
                source_ref=ip_stix_id,
                target_ref=as_stix_id,
            )
            _add(objects, seen, _to_plain(rel))

        # 3. Country
        country_code = data.get("country_code")  # e.g. "US"
        country_name = data.get("country")  # e.g. "United States"
        if country_code:
            country_name_lower = (country_name or country_code).lower().strip()
            country_stix_id = f"location--{uuid.uuid5(_OASIS_NAMESPACE, _canonical({'name': country_name_lower, 'x_ofm_location_type': 'Country'}))}"
            country_obj = stix2.Location(
                id=country_stix_id,
                name=country_name or country_code,
                country=country_code,
                allow_custom=True,
                x_ofm_location_type="Country",
                x_ofm_type="Country",
            )
            _add(objects, seen, _to_plain(country_obj))

            # IP located-at country
            rel_id = _make_rel_id(ip_stix_id, "located-at", country_stix_id)
            rel = stix2.Relationship(
                id=rel_id,
                relationship_type="located-at",
                source_ref=ip_stix_id,
                target_ref=country_stix_id,
            )
            _add(objects, seen, _to_plain(rel))

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

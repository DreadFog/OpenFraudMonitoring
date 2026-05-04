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
import logging
import uuid
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

# Deterministic UUIDv5 namespaces for stable STIX ids
_AS_NAMESPACE = uuid.UUID("b1c2d3e4-f5a6-4b7c-8d9e-0f1a2b3c4d5e")
_COUNTRY_NAMESPACE = uuid.UUID("7a3e4b2c-1d5f-4e8a-9c0b-2f6d8e7a1b3c")
_REL_NAMESPACE = uuid.UUID("c4d5e6f7-a8b9-4c0d-1e2f-3a4b5c6d7e8f")


def _detect_ip_type(ip: str) -> Optional[str]:
    try:
        v = ipaddress.ip_address(ip).version
        return "ipv4-addr" if v == 4 else "ipv6-addr"
    except (ValueError, TypeError):
        return None


def _make_rel_id(source_id: str, rel_type: str, target_id: str) -> str:
    key = f"{source_id}|{rel_type}|{target_id}"
    return f"relationship--{uuid.uuid5(_REL_NAMESPACE, key)}"


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
        ip_stix_id = f"{ip_type}--{uuid.uuid5(uuid.NAMESPACE_URL, ip)}"
        ip_obj = {
            "type": ip_type,
            "spec_version": "2.1",
            "id": ip_stix_id,
            "value": ip,
        }
        _add(objects, seen, ip_obj)

        # 2. Autonomous System
        asn_raw = data.get("asn")  # e.g. "AS15169"
        as_name = data.get("as_name")  # e.g. "Google LLC"
        if asn_raw:
            asn_number = int("".join(c for c in asn_raw if c.isdigit()) or "0")
            as_stix_id = f"autonomous-system--{uuid.uuid5(_AS_NAMESPACE, asn_raw)}"
            as_obj = {
                "type": "autonomous-system",
                "spec_version": "2.1",
                "id": as_stix_id,
                "number": asn_number,
                "name": as_name or asn_raw,
            }
            _add(objects, seen, as_obj)

            # IP belongs-to AS
            rel_id = _make_rel_id(ip_stix_id, "belongs-to", as_stix_id)
            _add(objects, seen, {
                "type": "relationship",
                "spec_version": "2.1",
                "id": rel_id,
                "relationship_type": "belongs-to",
                "source_ref": ip_stix_id,
                "target_ref": as_stix_id,
            })

        # 3. Country
        country_code = data.get("country_code")  # e.g. "US"
        country_name = data.get("country")  # e.g. "United States"
        if country_code:
            country_stix_id = f"location--{uuid.uuid5(_COUNTRY_NAMESPACE, country_code)}"
            country_obj = {
                "type": "location",
                "spec_version": "2.1",
                "id": country_stix_id,
                "name": country_name or country_code,
                "country": country_code,
            }
            _add(objects, seen, country_obj)

            # IP located-at country
            rel_id = _make_rel_id(ip_stix_id, "located-at", country_stix_id)
            _add(objects, seen, {
                "type": "relationship",
                "spec_version": "2.1",
                "id": rel_id,
                "relationship_type": "located-at",
                "source_ref": ip_stix_id,
                "target_ref": country_stix_id,
            })

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

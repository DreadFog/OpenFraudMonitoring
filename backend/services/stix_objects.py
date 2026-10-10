"""Normalize supported intelligence objects to the OFM STIX/OpenCTI contract."""

from datetime import datetime, timezone
import uuid


_OPENCTI_NAMESPACE = uuid.UUID("00abedb4-aa42-466c-9c01-fed23315a9b7")

_SDO_FIELDS = {
    "type", "spec_version", "id", "created_by_ref", "created", "modified",
    "revoked", "labels", "confidence", "lang", "external_references",
    "object_marking_refs", "granular_markings", "extensions",
}
_SCO_FIELDS = {
    "type", "spec_version", "id", "object_marking_refs",
    "granular_markings", "defanged", "extensions",
}
_TYPE_FIELDS = {
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
_SDO_TYPES = {"location", "indicator", "malware", "campaign", "intrusion-set"}
_SCO_TYPES = {"ipv4-addr", "ipv6-addr", "autonomous-system", "user-agent"}
_OPENCTI_TYPE_NAMES = {
    "ipv4-addr": "IPv4-Addr",
    "ipv6-addr": "IPv6-Addr",
    "autonomous-system": "Autonomous-System",
    "user-agent": "User-Agent",
    "location": "Country",
    "indicator": "Indicator",
    "malware": "Malware",
    "campaign": "Campaign",
    "intrusion-set": "Intrusion-Set",
    "relationship": "relationship",
}


def export_field_names(stix_type):
    common = _SCO_FIELDS if stix_type in _SCO_TYPES else _SDO_FIELDS
    fields = common | _TYPE_FIELDS.get(stix_type, set())
    return sorted(fields | {"stix_id", "created_at_platform", "source_connector_id"}
                  | ({"last_refreshed_at", "value"} if stix_type != "relationship" else set()))


def _timestamp(value, fallback=None):
    value = value or fallback
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
    else:
        parsed = None
    if parsed is None:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _opencti_id(stix_id):
    return str(uuid.uuid5(_OPENCTI_NAMESPACE, f"opencti:{stix_id}"))


def normalize_stix_object(obj, platform_created_at=None):
    """Return supported object's canonical STIX fields plus OpenCTI extensions."""
    if not isinstance(obj, dict):
        raise ValueError("STIX object must be a JSON object")
    stix_type = obj.get("type")
    if stix_type not in _TYPE_FIELDS:
        raise ValueError(f"unsupported STIX type: {stix_type!r}")
    stix_id = obj.get("id")
    if not isinstance(stix_id, str) or not stix_id:
        raise ValueError("STIX object id is required")

    is_sdo = stix_type in _SDO_TYPES
    is_sco = stix_type in _SCO_TYPES
    common_fields = _SDO_FIELDS if is_sdo or stix_type == "relationship" else _SCO_FIELDS
    allowed_fields = common_fields | _TYPE_FIELDS[stix_type]
    normalized = {
        key: value for key, value in obj.items()
        if key in allowed_fields or key.startswith("x_opencti_")
    }
    for key in (
        "string", "x_ofm_type", "x_ofm_location_type", "x_opencti_location_type",
        "_octi_created_at", "_octi_modified_at", "created_at", "modified_at",
    ):
        normalized.pop(key, None)

    normalized.update({"type": stix_type, "spec_version": "2.1", "id": stix_id})
    if is_sdo or stix_type == "relationship":
        created = _timestamp(
            obj.get("created") or obj.get("_octi_created_at") or obj.get("created_at"),
            platform_created_at,
        )
        modified = _timestamp(
            obj.get("modified") or obj.get("_octi_modified_at") or obj.get("modified_at"),
            created,
        )
        normalized["created"] = created
        normalized["modified"] = modified
        if normalized.get("revoked") is None:
            normalized["revoked"] = False
        if normalized.get("confidence") is None:
            normalized["confidence"] = 100
        if stix_type == "indicator":
            if not normalized.get("pattern_type"):
                normalized["pattern_type"] = "stix"
            if not normalized.get("valid_from"):
                normalized["valid_from"] = created
        elif stix_type == "malware":
            if normalized.get("is_family") is None:
                normalized["is_family"] = False
    else:
        normalized.pop("created", None)
        normalized.pop("modified", None)
        normalized.pop("revoked", None)
        normalized.setdefault("x_opencti_score", 50)

    for key in tuple(normalized):
        if normalized[key] is None:
            normalized.pop(key)

    if stix_type == "autonomous-system" and isinstance(normalized.get("number"), str):
        digits = "".join(character for character in normalized["number"] if character.isdigit())
        if not digits:
            raise ValueError("autonomous-system number must be an integer")
        normalized["number"] = int(digits)

    normalized["x_opencti_id"] = normalized.get("x_opencti_id") or _opencti_id(stix_id)
    fallback_type = (
        normalized.get("relationship_type", "relationship")
        if stix_type == "relationship"
        else _OPENCTI_TYPE_NAMES[stix_type]
    )
    normalized["x_opencti_type"] = normalized.get("x_opencti_type") or fallback_type

    if stix_type == "user-agent":
        if not normalized.get("value"):
            normalized["value"] = obj.get("string")
        normalized.pop("string", None)
    elif stix_type == "location":
        if obj.get("x_ofm_location_type") or obj.get("x_opencti_location_type"):
            normalized["x_opencti_location_type"] = "Country"
        if obj.get("x_opencti_aliases") is not None:
            normalized["x_opencti_aliases"] = obj["x_opencti_aliases"]

    _validate_minimum_properties(normalized)
    return normalized


def _validate_minimum_properties(obj):
    stix_type = obj["type"]
    required = {
        "ipv4-addr": ("value",),
        "ipv6-addr": ("value",),
        "autonomous-system": ("number",),
        "user-agent": ("value",),
        "campaign": ("name",),
        "intrusion-set": ("name",),
        "indicator": ("pattern", "valid_from", "pattern_type"),
        "malware": ("is_family",),
        "relationship": ("relationship_type", "source_ref", "target_ref"),
    }
    for field in required.get(stix_type, ()):
        if field not in obj:
            raise ValueError(f"{stix_type} STIX object requires {field}")
    if stix_type == "location" and not (
        obj.get("region") or obj.get("country")
        or (obj.get("latitude") is not None and obj.get("longitude") is not None)
    ):
        raise ValueError("location STIX object requires region, country, or coordinates")
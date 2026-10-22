"""Admin edits of stored STIX entities from the Intelligence view."""

from datetime import datetime, timedelta, timezone

from services.indicator_generation import format_timestamp, parse_timestamp
from services.indicator_revocation import apply_indicator_revocation
from services.intel_ingest import stix_model_and_value
from services.stix_objects import normalize_stix_object


# The platform value is the lookup key used by sessions and enrichment for these types.
IMMUTABLE_VALUE_TYPES = {"ipv4-addr", "ipv6-addr", "user-agent", "autonomous-system", "location"}


class EntityEditError(ValueError):
    pass


def update_entity(row, stix_type, stix_object, now=None):
    """Replace a row's STIX object; caller locks the row and owns the transaction."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(stix_object, dict):
        raise EntityEditError("stix_object must be a JSON object")
    if stix_object.get("type") != stix_type or stix_object.get("id") != row.stix_id:
        raise EntityEditError("type and id cannot be changed")
    try:
        normalized = normalize_stix_object(stix_object)
    except ValueError as error:
        raise EntityEditError(str(error)) from error
    resolved = stix_model_and_value(normalized)
    if resolved is None or not isinstance(row, resolved[0]):
        raise EntityEditError("object no longer matches its entity type")
    value = resolved[1]
    if not isinstance(value, str) or not value:
        raise EntityEditError("object has no usable value")
    if stix_type in IMMUTABLE_VALUE_TYPES and value != row.value:
        raise EntityEditError(f"the value of a {stix_type} entity cannot be changed")

    previous = row.raw or {}
    if "created" in normalized:
        normalized["created"] = previous.get("created", normalized["created"])
        normalized["modified"] = format_timestamp(now)
    if stix_type == "indicator":
        try:
            valid_from = parse_timestamp(normalized["valid_from"])
            valid_until = parse_timestamp(normalized["valid_until"]) if normalized.get("valid_until") else None
        except (AttributeError, TypeError, ValueError) as error:
            raise EntityEditError("valid_from and valid_until must be ISO 8601 timestamps") from error
        if valid_until is not None and valid_until <= valid_from:
            raise EntityEditError("valid_until must be later than valid_from")
        if not isinstance(normalized.get("revoked"), bool):
            raise EntityEditError("revoked must be true or false")
        row.name = normalized.get("name")
        row.description = normalized.get("description")
        row.revoked = normalized["revoked"]
    row.raw = normalized
    row.value = value[:2048]
    if stix_type == "indicator":
        apply_indicator_revocation([row], now=now, commit=False)
    return row


def revoke_indicator(row, now=None):
    """Mark an indicator revoked and end its validity now; returns False if already done."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    now = now.replace(microsecond=now.microsecond // 1000 * 1000)
    raw = dict(row.raw or {})
    try:
        current_until = parse_timestamp(raw["valid_until"]) if raw.get("valid_until") else None
        valid_from = parse_timestamp(raw["valid_from"]) if raw.get("valid_from") else None
    except (AttributeError, TypeError, ValueError):
        current_until = valid_from = None
    if raw.get("revoked") is True and row.revoked and current_until is not None and current_until <= now:
        return False
    stamp = format_timestamp(now)
    raw.update(revoked=True, modified=stamp, valid_until=stamp)
    # STIX requires valid_until > valid_from; pull a future start back just before revocation.
    if valid_from is None or valid_from >= now:
        raw["valid_from"] = format_timestamp(now - timedelta(milliseconds=1))
    row.raw = raw
    row.revoked = True
    return True

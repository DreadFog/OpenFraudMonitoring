"""STIX filter schema + query helpers for intelligence and TAXII use-cases."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, or_, func

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
)


TYPE_TO_MODEL = {
    "ipv4-addr": StixIPv4Addr,
    "ipv6-addr": StixIPv6Addr,
    "user-agent": StixUserAgent,
    "autonomous-system": StixAutonomousSystem,
    "location": StixCountry,
    "indicator": StixIndicator,
    "malware": StixMalware,
    "campaign": StixCampaign,
    "intrusion-set": StixIntrusionSet,
}


OPERATORS = {
    "string": ["eq", "neq", "contains", "not_contains", "starts_with", "ends_with"],
    "number": ["eq", "neq", "gt", "gte", "lt", "lte"],
    "boolean": ["eq"],
    "date": ["eq", "gt", "gte", "lt", "lte"],
}


def _common_fields(Model):
    return [
        {"name": "value", "label": "Value", "type": "string", "expr": Model.value},
        {"name": "stix_id", "label": "STIX ID", "type": "string", "expr": Model.stix_id},
        {"name": "decayed", "label": "Decayed", "type": "boolean", "expr": Model.decayed},
        {
            "name": "source_connector_id",
            "label": "Source Connector ID",
            "type": "number",
            "expr": Model.source_connector_id,
        },
        {
            "name": "created_at_platform",
            "label": "Created On Platform",
            "type": "date",
            "expr": Model.created_at_platform,
        },
        {
            "name": "last_refreshed_at",
            "label": "Last Refreshed",
            "type": "date",
            "expr": Model.last_refreshed_at,
        },
    ]


def _type_specific_fields(stix_type: str, Model):
    fields = []
    if stix_type == "autonomous-system":
        fields.append({
            "name": "asn_number",
            "label": "AS Number",
            "type": "number",
            "expr": Model.raw["number"].astext,
        })
        fields.append({
            "name": "asn_name",
            "label": "AS Name",
            "type": "string",
            "expr": Model.raw["name"].astext,
        })
    elif stix_type == "location":
        fields.append({
            "name": "country_code",
            "label": "Country Code",
            "type": "string",
            "expr": Model.raw["country"].astext,
        })
        fields.append({
            "name": "country_name",
            "label": "Country Name",
            "type": "string",
            "expr": Model.raw["name"].astext,
        })
        fields.append({
            "name": "location_type",
            "label": "Location Type",
            "type": "string",
            "expr": func.coalesce(Model.raw["x_ofm_location_type"].astext, Model.raw["x_opencti_location_type"].astext),
        })
    elif stix_type == "indicator":
        fields.append({
            "name": "pattern",
            "label": "Pattern",
            "type": "string",
            "expr": Model.raw["pattern"].astext,
        })
        fields.append({
            "name": "name",
            "label": "Name",
            "type": "string",
            "expr": Model.raw["name"].astext,
        })
    elif stix_type in ("malware", "campaign", "intrusion-set"):
        fields.append({
            "name": "name",
            "label": "Name",
            "type": "string",
            "expr": Model.raw["name"].astext,
        })
    elif stix_type == "user-agent":
        fields.append({
            "name": "string",
            "label": "User-Agent String",
            "type": "string",
            "expr": func.coalesce(Model.raw["string"].astext, Model.raw["value"].astext),
        })
    return fields


def get_filter_schema(stix_type: str):
    Model = TYPE_TO_MODEL.get(stix_type)
    if Model is None:
        return None
    fields = _common_fields(Model) + _type_specific_fields(stix_type, Model)
    return [
        {
            "name": f["name"],
            "label": f["label"],
            "type": f["type"],
            "operators": OPERATORS[f["type"]],
        }
        for f in fields
    ]


def _field_meta(stix_type: str, field_name: str):
    Model = TYPE_TO_MODEL.get(stix_type)
    if Model is None:
        return None
    for f in _common_fields(Model) + _type_specific_fields(stix_type, Model):
        if f["name"] == field_name:
            return f
    return None


def _to_bool(value):
    return str(value).strip().lower() in ("true", "1", "yes")


def _to_number(value):
    return float(value)


def _to_datetime(value):
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _cast_value(value, field_type: str):
    if field_type == "boolean":
        return _to_bool(value)
    if field_type == "number":
        return _to_number(value)
    if field_type == "date":
        return _to_datetime(value)
    return str(value)


def _build_condition(expr, op: str, value, field_type: str):
    if op not in OPERATORS[field_type]:
        return None

    try:
        typed = _cast_value(value, field_type)
    except (ValueError, TypeError):
        return None

    if field_type == "string":
        if op == "eq":
            return expr == typed
        if op == "neq":
            return expr != typed
        if op == "contains":
            return expr.ilike(f"%{typed}%")
        if op == "not_contains":
            return ~expr.ilike(f"%{typed}%")
        if op == "starts_with":
            return expr.ilike(f"{typed}%")
        if op == "ends_with":
            return expr.ilike(f"%{typed}")

    if op == "eq":
        return expr == typed
    if op == "neq":
        return expr != typed
    if op == "gt":
        return expr > typed
    if op == "gte":
        return expr >= typed
    if op == "lt":
        return expr < typed
    if op == "lte":
        return expr <= typed
    return None


def apply_filters(query, stix_type: str, filters, logic: str = "AND"):
    if not filters:
        return query, None

    combiner = and_ if str(logic).upper() != "OR" else or_
    conditions = []

    for item in filters:
        if not isinstance(item, dict):
            return query, "invalid filter format"
        field_name = (item.get("field") or "").strip()
        op = (item.get("op") or "").strip()
        value = item.get("value")
        if not field_name or not op:
            return query, "field and op are required for each filter"

        meta = _field_meta(stix_type, field_name)
        if meta is None:
            return query, f"unknown filter field '{field_name}' for type '{stix_type}'"

        cond = _build_condition(meta["expr"], op, value, meta["type"])
        if cond is None:
            return query, f"invalid operator/value for field '{field_name}'"

        conditions.append(cond)

    if not conditions:
        return query, None

    return query.filter(combiner(*conditions)), None

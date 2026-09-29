"""
Device filter schema — generated from the Device model's columns, plus
aggregate fields computed from linked sessions.
"""

from sqlalchemy import Boolean, Float, Integer, String, and_, func, or_, select

from models import Session
from models.device import Device
from schema_registry import OPERATORS
from rules.engine import apply_operator

_COLUMN_TYPES = ((Boolean, "boolean"), (Integer, "number"), (Float, "number"), (String, "string"))

# Stored as epoch milliseconds, so exposed as dates rather than plain numbers.
_DATE_COLUMNS = {"first_seen", "last_seen"}

_CATEGORIES = {
    "Identity": {"id", "cookie_id", "device_bucket", "confidence", "device_type", "is_mobile"},
    "Hardware": {
        "platform", "screen_width", "screen_height", "pixel_depth", "color_depth",
        "speakers", "microphones", "webcams", "webgl_vendor", "webgl_renderer",
        "hev_architecture", "hev_bitness", "hev_model",
    },
    "OS / Browser": {
        "hev_platform", "hev_platform_version", "timezone", "language",
        "audio_codec_hash", "video_codec_hash",
    },
    "Activity": _DATE_COLUMNS,
}

_LABELS = {
    "id": "Device ID",
    "cookie_id": "Cookie ID",
    "webgl_vendor": "WebGL vendor",
    "webgl_renderer": "WebGL renderer",
    "hev_architecture": "Architecture (client hints)",
    "hev_bitness": "Bitness (client hints)",
    "hev_model": "Model (client hints)",
    "hev_platform": "Platform (client hints)",
    "hev_platform_version": "Platform version (client hints)",
}


def _field_type(column):
    if column.name in _DATE_COLUMNS:
        return "date"
    for sql_type, name in _COLUMN_TYPES:
        if isinstance(column.type, sql_type):
            return name
    return None


def _category(name):
    return next((cat for cat, names in _CATEGORIES.items() if name in names), "Device")


def _linked(expr):
    return select(expr).where(Session.device_id == Device.id).correlate(Device).scalar_subquery()


_AGGREGATES = {
    "sessions_count": ("Linked sessions", lambda: _linked(func.count(Session.id))),
    "distinct_fsids": ("Distinct fsids", lambda: _linked(func.count(func.distinct(Session.fsid)))),
    "distinct_ips": ("Distinct IPs", lambda: _linked(func.count(func.distinct(Session.client_ip)))),
}


def _build_fields():
    fields = {}
    for column in Device.__table__.columns:
        field_type = _field_type(column)
        if field_type is None:
            continue
        fields[column.name] = {
            "name": column.name,
            "label": _LABELS.get(column.name, column.name.replace("_", " ").capitalize()),
            "type": field_type,
            "category": _category(column.name),
            "expr": lambda c=column.name: getattr(Device, c),
            "suggest": field_type == "string",
        }
    for name, (label, expr) in _AGGREGATES.items():
        fields[name] = {
            "name": name, "label": label, "type": "number",
            "category": "Linked sessions", "expr": expr, "suggest": False,
        }
    return fields


DEVICE_FIELDS = _build_fields()


def get_device_schema():
    return [
        {
            "name": f["name"],
            "label": f["label"],
            "type": f["type"],
            "category": f["category"],
            "operators": OPERATORS[f["type"]],
        }
        for f in DEVICE_FIELDS.values()
    ]


def build_device_query(filters, logic="AND", base_query=None):
    """Apply {field, op, value} filters to a Device query; unknown fields are ignored."""
    query = base_query if base_query is not None else Device.query
    conditions = []
    for f in filters or []:
        if not isinstance(f, dict):
            continue
        meta = DEVICE_FIELDS.get(f.get("field"))
        if meta is None:
            continue
        cond = apply_operator(meta["expr"](), meta["type"], f.get("op"), f.get("value", ""))
        if cond is not None:
            conditions.append(cond)
    if conditions:
        query = query.filter((or_ if logic == "OR" else and_)(*conditions))
    return query


def suggest_device_values(field_name, q="", limit=20):
    meta = DEVICE_FIELDS.get(field_name)
    if meta is None:
        return []
    if meta["type"] == "boolean":
        return [o for o in ("true", "false") if q.lower() in o]
    if not meta["suggest"]:
        return []
    column = meta["expr"]()
    query = Device.query.with_entities(column).distinct().filter(column.isnot(None), column != "")
    if q:
        query = query.filter(column.ilike(f"%{q}%"))
    return [row[0] for row in query.limit(limit).all()]

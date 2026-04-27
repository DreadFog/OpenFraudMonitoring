"""
Schema registry — auto-built from FPScanner's types.ts via generate_schema.py.

This module is the single source of truth for what fields can be filtered on,
what operators are available for each type, and which table/column they map to.

To regenerate after FPScanner updates:
    python generate_schema.py
"""

from _generated_schema import SIGNAL_FIELDS, DETECTION_FIELDS, TOP_LEVEL_FIELDS

OPERATORS = {
    "string": [
        {"name": "eq", "label": "="},
        {"name": "neq", "label": "≠"},
        {"name": "contains", "label": "contains"},
        {"name": "not_contains", "label": "not contains"},
        {"name": "starts_with", "label": "starts with"},
        {"name": "ends_with", "label": "ends with"},
    ],
    "number": [
        {"name": "eq", "label": "="},
        {"name": "neq", "label": "≠"},
        {"name": "gt", "label": ">"},
        {"name": "gte", "label": "≥"},
        {"name": "lt", "label": "<"},
        {"name": "lte", "label": "≤"},
    ],
    "boolean": [
        {"name": "eq", "label": "="},
    ],
    "date": [
        {"name": "gt", "label": ">"},
        {"name": "gte", "label": "≥"},
        {"name": "lt", "label": "<"},
        {"name": "lte", "label": "≤"},
        {"name": "eq", "label": "="},
    ],
}

# ── Build SCHEMA_FIELDS from the generated data ──

SCHEMA_FIELDS = [
    # Session-level fields (always present)
    {"name": "client_ip", "label": "Client IP", "type": "string", "model": "Session", "column": "client_ip"},
    {"name": "risk_score", "label": "Risk Score", "type": "number", "model": "Session", "column": "risk_score"},
    {"name": "fsid", "label": "Fingerprint ID (fsid)", "type": "string", "model": "Session", "column": "fsid"},
    {"name": "first_seen", "label": "First Seen", "type": "date", "model": "Session", "column": "first_seen"},
    {"name": "last_seen", "label": "Last Seen", "type": "date", "model": "Session", "column": "last_seen"},
]

# Top-level fingerprint fields
for f in TOP_LEVEL_FIELDS:
    SCHEMA_FIELDS.append({
        "name": f["column"],
        "label": f["label"],
        "type": f["type"],
        "model": "Fingerprint",
        "column": f["column"],
    })

# Signal fields (denormalized from signals.*)
for f in SIGNAL_FIELDS:
    SCHEMA_FIELDS.append({
        "name": f["column"],
        "label": f["label"],
        "type": f["type"],
        "model": "Fingerprint",
        "column": f["column"],
    })

# Detection fields (denormalized from fastBotDetectionDetails.*)
for f in DETECTION_FIELDS:
    SCHEMA_FIELDS.append({
        "name": f["column"],
        "label": f["label"],
        "type": f["type"],
        "model": "Fingerprint",
        "column": f["column"],
    })

# ── Dedup (fsid appears in both session and top-level) ──
_seen = set()
_deduped = []
for f in SCHEMA_FIELDS:
    if f["name"] not in _seen:
        _seen.add(f["name"])
        _deduped.append(f)
SCHEMA_FIELDS = _deduped


def get_schema():
    """Return schema description for API consumers (frontend filter builder, etc.)."""
    return [
        {
            "name": f["name"],
            "label": f["label"],
            "type": f["type"],
            "operators": OPERATORS[f["type"]],
        }
        for f in SCHEMA_FIELDS
    ]


def get_field_meta(field_name):
    """Get full metadata for a field by name. Returns None if unknown."""
    for f in SCHEMA_FIELDS:
        if f["name"] == field_name:
            return f
    return None

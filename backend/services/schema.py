"""
Schema registry - defines all queryable fields for filters and rules.

This module is the single source of truth for what fields can be filtered on,
what operators are available for each type, and which table/column they map to.
"""

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
}

SCHEMA_FIELDS = [
    # ── Session-level fields ──
    {"name": "client_ip", "label": "Client IP", "type": "string", "model": "Session", "column": "client_ip"},
    {"name": "risk_score", "label": "Risk Score", "type": "number", "model": "Session", "column": "risk_score"},
    {"name": "device_id", "label": "Device ID", "type": "string", "model": "Session", "column": "device_id"},

    # ── Fingerprint-level fields (denormalized) ──
    {"name": "user_agent", "label": "User Agent", "type": "string", "model": "Fingerprint", "column": "user_agent"},
    {"name": "platform", "label": "Platform", "type": "string", "model": "Fingerprint", "column": "platform"},
    {"name": "language", "label": "Language", "type": "string", "model": "Fingerprint", "column": "language"},
    {"name": "operating_system", "label": "Operating System", "type": "string", "model": "Fingerprint", "column": "operating_system"},
    {"name": "timezone", "label": "Timezone", "type": "string", "model": "Fingerprint", "column": "timezone"},
    {"name": "public_ip", "label": "Public IP", "type": "string", "model": "Fingerprint", "column": "public_ip"},
    {"name": "webgl_vendor", "label": "WebGL Vendor", "type": "string", "model": "Fingerprint", "column": "webgl_vendor"},
    {"name": "webgl_renderer", "label": "WebGL Renderer", "type": "string", "model": "Fingerprint", "column": "webgl_renderer"},
    {"name": "screen_width", "label": "Screen Width", "type": "number", "model": "Fingerprint", "column": "screen_width"},
    {"name": "screen_height", "label": "Screen Height", "type": "number", "model": "Fingerprint", "column": "screen_height"},
    {"name": "hardware_concurrency", "label": "CPU Cores", "type": "number", "model": "Fingerprint", "column": "hardware_concurrency"},
    {"name": "device_memory", "label": "Device Memory (GB)", "type": "number", "model": "Fingerprint", "column": "device_memory"},
    {"name": "color_depth", "label": "Color Depth", "type": "number", "model": "Fingerprint", "column": "color_depth"},
    {"name": "is_mobile", "label": "Is Mobile", "type": "boolean", "model": "Fingerprint", "column": "is_mobile"},
    {"name": "is_workstation", "label": "Is Workstation", "type": "boolean", "model": "Fingerprint", "column": "is_workstation"},
    {"name": "has_webdriver", "label": "Has WebDriver", "type": "boolean", "model": "Fingerprint", "column": "has_webdriver"},
    {"name": "has_phantom", "label": "Has PhantomJS", "type": "boolean", "model": "Fingerprint", "column": "has_phantom"},
    {"name": "has_nightmare", "label": "Has Nightmare", "type": "boolean", "model": "Fingerprint", "column": "has_nightmare"},
    {"name": "has_puppeteer", "label": "Has Puppeteer", "type": "boolean", "model": "Fingerprint", "column": "has_puppeteer"},
    {"name": "has_selenium", "label": "Has Selenium", "type": "boolean", "model": "Fingerprint", "column": "has_selenium"},
    {"name": "has_chromedriver", "label": "Has ChromeDriver", "type": "boolean", "model": "Fingerprint", "column": "has_chromedriver"},
    {"name": "has_empty_languages", "label": "Empty Languages", "type": "boolean", "model": "Fingerprint", "column": "has_empty_languages"},
    {"name": "has_no_plugins", "label": "No Plugins", "type": "boolean", "model": "Fingerprint", "column": "has_no_plugins"},
    {"name": "has_native_spoofed", "label": "Native Spoofed", "type": "boolean", "model": "Fingerprint", "column": "has_native_spoofed"},
    {"name": "has_canvas", "label": "Has Canvas", "type": "boolean", "model": "Fingerprint", "column": "has_canvas"},
    {"name": "has_audio", "label": "Has Audio", "type": "boolean", "model": "Fingerprint", "column": "has_audio"},
]


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

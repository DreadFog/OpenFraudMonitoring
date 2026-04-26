#!/usr/bin/env python3
"""
Schema generator — parses FPScanner's types.ts and produces a Python schema
module (_generated_schema.py) that the backend consumes.

Run this script whenever FPScanner updates their types:
    python generate_schema.py

It reads:
    fpscanner_ref/types.ts   (symlink → fpscanner/src/types.ts)

It produces:
    _generated_schema.py     (auto-generated, do not edit manually)
"""

import re
import os
import json
from pathlib import Path
from datetime import datetime, timezone

TYPES_TS = Path(__file__).parent / "fpscanner_ref" / "types.ts"
OUTPUT = Path(__file__).parent / "_generated_schema.py"


# ── TypeScript parser ────────────────────────────────────────────────────────

def parse_interfaces(source: str) -> dict[str, list[tuple[str, str]]]:
    """
    Parse all TypeScript interfaces from source.
    Returns {InterfaceName: [(fieldName, rawTypeAnnotation), ...]}
    """
    interfaces = {}
    # Match interface blocks (handles extends too)
    pattern = re.compile(
        r"export\s+interface\s+(\w+)(?:\s+extends\s+\w+)?\s*\{([^}]+)\}",
        re.DOTALL,
    )
    for m in pattern.finditer(source):
        name = m.group(1)
        body = m.group(2)
        fields = []
        for line in body.strip().splitlines():
            line = line.strip().rstrip(";").strip()
            if not line or line.startswith("//"):
                continue
            # field?: Type  or  field: Type
            fm = re.match(r"(\w+)\??\s*:\s*(.+)", line)
            if fm:
                fields.append((fm.group(1), fm.group(2).strip()))
        interfaces[name] = fields
    return interfaces


def resolve_base_type(raw_type: str) -> str:
    """
    Resolve a TypeScript type annotation to a Python-schema type.
    SignalValue<T> → the inner T.
    """
    # Unwrap SignalValue<...>
    sv = re.match(r"SignalValue<(.+)>", raw_type)
    inner = sv.group(1) if sv else raw_type

    # Normalize
    inner = inner.strip()
    if inner in ("boolean", "boolean | 'NA'"):
        return "boolean"
    if inner in ("number", "number | 'NA'"):
        return "number"
    if inner in ("string", "string | null", "string | null | 'NA'"):
        return "string"
    if inner.startswith("string["):
        return "string[]"
    return inner  # interface reference


def is_primitive(ts_type: str) -> bool:
    return ts_type in ("boolean", "number", "string", "string[]")


# ── Flattening logic ────────────────────────────────────────────────────────

def flatten_signals(
    interfaces: dict,
    iface_name: str,
    prefix: str = "",
) -> list[dict]:
    """
    Recursively flatten an interface into a list of leaf fields with
    dot-separated paths (e.g. "device.screenResolution.width").
    """
    fields_out = []
    iface_fields = interfaces.get(iface_name, [])

    for field_name, raw_type in iface_fields:
        path = f"{prefix}.{field_name}" if prefix else field_name
        base = resolve_base_type(raw_type)

        if is_primitive(base):
            fields_out.append({"path": path, "type": base})
        elif base in interfaces:
            # Recurse into sub-interface
            fields_out.extend(flatten_signals(interfaces, base, path))
        else:
            # Unknown compound — store as string (JSON blob)
            fields_out.append({"path": path, "type": "string"})

    return fields_out


def flatten_detections(interfaces: dict) -> list[dict]:
    """
    Flatten FastBotDetectionDetails into boolean fields with severity metadata.
    """
    det_fields = interfaces.get("FastBotDetectionDetails", [])
    out = []
    for field_name, _raw_type in det_fields:
        out.append({
            "name": field_name,
            "path": f"fastBotDetectionDetails.{field_name}.detected",
            "type": "boolean",
        })
    return out


# ── Column name generation ───────────────────────────────────────────────────

def _camel_to_snake(name: str) -> str:
    """
    Convert camelCase / PascalCase to snake_case, handling acronyms properly.
    e.g. "webGL" → "webgl", "hasCDP" → "has_cdp", "screenResolution" → "screen_resolution"
    """
    # Insert underscore between lowercase/digit and uppercase
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    # Insert underscore between consecutive uppercase and lowercase (handles acronyms)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    return s.lower()


def path_to_column(path: str) -> str:
    """
    Convert a dotted signal path to a snake_case column name.
    e.g. "device.screenResolution.width" → "device_screen_resolution_width"
         "graphics.webGL.vendor" → "graphics_webgl_vendor"
    """
    parts = path.split(".")
    return "_".join(_camel_to_snake(p) for p in parts)


def path_to_label(path: str) -> str:
    """
    Convert a dotted signal path to a human-readable label.
    e.g. "device.screenResolution.width" → "Device > Screen Resolution > Width"
         "graphics.webGL.vendor" → "Graphics > WebGL > Vendor"
    """
    # Known acronym replacements for labels
    ACRONYMS = {"webgl": "WebGL", "webgpu": "WebGPU", "cdp": "CDP", "cpu": "CPU",
                "gpu": "GPU", "utc": "UTC", "etsl": "ETSL", "ip": "IP",
                "rtc": "RTC", "usb": "USB", "otp": "OTP", "ua": "UA",
                "fsid": "FSID"}

    parts = path.split(".")
    labels = []
    for p in parts:
        # Check the whole segment first (e.g. "webGL" → "WebGL")
        if p.lower() in ACRONYMS:
            labels.append(ACRONYMS[p.lower()])
            continue
        # camelCase → spaced words
        spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", p)
        spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
        # Title-case each word, then replace known acronyms
        words = spaced.split()
        titled = []
        for w in words:
            low = w.lower()
            if low in ACRONYMS:
                titled.append(ACRONYMS[low])
            else:
                titled.append(w.capitalize())
        labels.append(" ".join(titled))
    return " > ".join(labels)


# ── Schema type mapping ─────────────────────────────────────────────────────

def ts_type_to_sqlalchemy(ts_type: str) -> str:
    """Map TypeScript type to SQLAlchemy column type string."""
    if ts_type == "boolean":
        return "db.Boolean"
    if ts_type == "number":
        return "db.Float"
    if ts_type == "string":
        return "db.String(512)"
    if ts_type == "string[]":
        return "JSONB"
    return "db.String(512)"


def ts_type_to_default(ts_type: str) -> str:
    if ts_type == "boolean":
        return "False"
    if ts_type == "number":
        return "0"
    if ts_type == "string":
        return '""'
    if ts_type == "string[]":
        return "list"
    return '""'


def ts_type_to_schema_type(ts_type: str) -> str:
    if ts_type == "boolean":
        return "boolean"
    if ts_type == "number":
        return "number"
    return "string"


# ── Code generation ──────────────────────────────────────────────────────────

def generate(source: str) -> str:
    interfaces = parse_interfaces(source)

    # 1. Flatten signals (under FingerprintSignals)
    signal_fields = flatten_signals(interfaces, "FingerprintSignals")

    # 2. Flatten detection details
    detection_fields = flatten_detections(interfaces)

    # 3. Build output
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        '"""',
        f"Auto-generated from fpscanner_ref/types.ts on {now}.",
        "DO NOT EDIT — run `python generate_schema.py` to regenerate.",
        '"""',
        "",
        "# ── Signal fields (from FingerprintSignals interface) ──",
        "",
        "SIGNAL_FIELDS = [",
    ]

    for f in signal_fields:
        col = path_to_column(f["path"])
        label = path_to_label(f["path"])
        schema_type = ts_type_to_schema_type(f["type"])
        lines.append(
            f'    {{"path": "{f["path"]}", "column": "{col}", '
            f'"label": "{label}", "type": "{schema_type}", '
            f'"sa_type": "{ts_type_to_sqlalchemy(f["type"])}", '
            f'"default": {ts_type_to_default(f["type"])}}},'
        )
    lines.append("]")
    lines.append("")

    # Detection fields
    lines.append("# ── Detection fields (from FastBotDetectionDetails) ──")
    lines.append("")
    lines.append("DETECTION_FIELDS = [")
    for d in detection_fields:
        col = f"det_{path_to_column(d['name'])}"
        label = path_to_label(d["name"])
        lines.append(
            f'    {{"name": "{d["name"]}", "path": "{d["path"]}", '
            f'"column": "{col}", "label": "Det: {label}", "type": "boolean"}},'
        )
    lines.append("]")
    lines.append("")

    # Top-level fingerprint fields
    lines.append("# ── Top-level fingerprint fields ──")
    lines.append("")
    lines.append("TOP_LEVEL_FIELDS = [")
    lines.append('    {"path": "fsid", "column": "fsid", "label": "Fingerprint ID (fsid)", "type": "string"},')
    lines.append('    {"path": "fastBotDetection", "column": "fast_bot_detection", "label": "Fast Bot Detection", "type": "boolean"},')
    lines.append('    {"path": "url", "column": "url", "label": "Page URL", "type": "string"},')
    lines.append("]")
    lines.append("")

    # Detection names list (for seed_rules)
    lines.append("# ── Detection rule names (for seeding) ──")
    lines.append("")
    lines.append("DETECTION_NAMES = [")
    for d in detection_fields:
        lines.append(f'    "{d["name"]}",')
    lines.append("]")
    lines.append("")

    return "\n".join(lines) + "\n"


def main():
    if not TYPES_TS.exists():
        print(f"ERROR: {TYPES_TS} not found. Did you create the symlink?")
        print("  ln -s /path/to/fpscanner/src/types.ts fpscanner_ref/types.ts")
        raise SystemExit(1)

    source = TYPES_TS.read_text()
    code = generate(source)
    OUTPUT.write_text(code)
    print(f"Generated {OUTPUT} from {TYPES_TS}")
    print(f"  Signal fields:    {code.count('path')} entries")


if __name__ == "__main__":
    main()

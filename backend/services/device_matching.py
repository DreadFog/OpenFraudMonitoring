"""
Device matching — conservative resolution of a Device identity cluster.

Unlike `Session.fsid` (a repeatable but volatile fingerprint value that may
appear on multiple visits), a Device requires agreement across three hardware
evidence groups.

Resolution order (highest confidence first):
  1. Client-side device UUID — retain the original association confidence.
  2. Graphics/model, display, and capacity agree with exactly one immutable
      creation profile, with no credible hardware contradictions → link.
  3. Missing, conflicting, or ambiguous evidence → create a new Device.

See docs/devices.md for the full rationale and field tiering.
"""

import logging
import math
import re
from types import SimpleNamespace

from services.database import db
from models.device import Device, DeviceCookie, MAX_RECENT_IPS

logger = logging.getLogger(__name__)

# ── Field tiers ──
# (device attribute, denormalized Fingerprint column)
# Tier A — hardware-bound identity fields.
_TIER_A_FIELDS = [
    ("platform", "device_platform"),
    ("screen_width", "device_screen_resolution_width"),
    ("screen_height", "device_screen_resolution_height"),
    ("pixel_depth", "device_screen_resolution_pixel_depth"),
    ("color_depth", "device_screen_resolution_color_depth"),
    ("cpu_count", "device_cpu_count"),
    ("memory", "device_memory"),
    ("speakers", "device_multimedia_devices_speakers"),
    ("microphones", "device_multimedia_devices_microphones"),
    ("webcams", "device_multimedia_devices_webcams"),
    ("webgl_vendor", "graphics_web_gl_vendor"),
    ("webgl_renderer", "graphics_web_gl_renderer"),
    ("hev_architecture", "browser_high_entropy_values_architecture"),
    ("hev_bitness", "browser_high_entropy_values_bitness"),
    ("hev_model", "browser_high_entropy_values_model"),
]

# Tier B — OS/browser-bound supporting fields.
_TIER_B_FIELDS = [
    ("hev_platform", "browser_high_entropy_values_platform"),
    ("hev_platform_version", "browser_high_entropy_values_platform_version"),
    ("timezone", "locale_internationalization_timezone"),
    ("language", "locale_languages_language"),
    ("audio_codec_hash", "codecs_audio_can_play_type_hash"),
    ("video_codec_hash", "codecs_video_can_play_type_hash"),
]

CANONICAL_FIELDS = _TIER_A_FIELDS + _TIER_B_FIELDS

# Platforms that are unambiguously desktop/workstation.
_WORKSTATION_PLATFORMS = {
    "Win32", "Win64",
    "MacIntel", "MacPPC",
    "Linux x86_64", "Linux x86-64", "Linux aarch64",
    "Linux armv81", "Linux armv8l",
    "FreeBSD amd64",
}

# Fields spoofed by Firefox's Resist Fingerprinting (RFP) protection: screen
# width/height are derived from the content viewport (not real hardware) and
# drift with window size/zoom, so they're excluded for Firefox — see
# docs/devices.md.
_RFP_VOLATILE_FIELDS = {"screen_width", "screen_height"}

def _is_firefox(denorm):
    ua = str(denorm.get("browser_user_agent") or "")
    return "Firefox" in ua and "Seamonkey" not in ua


def _volatile_fields_for(denorm):
    """Fields that shouldn't be trusted for this particular reading."""
    return _RFP_VOLATILE_FIELDS if _is_firefox(denorm) else set()


def derive_device_type(denorm):
    """Classify a device as 'mobile', 'workstation', or 'unknown' from its signals.

    Signals checked (in priority order):
      1. highEntropyValues.mobile == False → explicit non-mobile from UA-CH
      2. platform in known desktop set       → unambiguous desktop OS/arch
      3. pointer==fine AND hover==True       → mouse+hover = desktop-class input
    Falls back to 'mobile' if highEntropyValues.mobile is explicitly True,
    otherwise 'unknown'.
    """
    is_mobile = denorm.get("browser_high_entropy_values_mobile") is True

    is_workstation = False
    if denorm.get("browser_high_entropy_values_mobile") is False:
        is_workstation = True
    elif denorm.get("device_platform") in _WORKSTATION_PLATFORMS:
        is_workstation = True
    elif denorm.get("device_media_queries_pointer") == "fine" and denorm.get("device_media_queries_hover") is True:
        is_workstation = True

    device_type = "mobile" if is_mobile else ("workstation" if is_workstation else "unknown")
    return is_mobile, device_type


def _norm(value):
    if value is None:
        return ""
    return str(value)


def make_bucket(denorm):
    """Build the legacy device-bucket summary; matching does not use it."""
    platform = _norm(denorm.get("device_platform")) or "unknown"
    if _is_firefox(denorm):
        # Screen dims are RFP-spoofed and drift with window size — fall back
        # to GPU renderer for a bucket key that isn't tied to window state.
        renderer = _norm(denorm.get("graphics_web_gl_renderer")) or "unknown-gpu"
        return f"{platform}|firefox-rfp|{renderer}"
    width = int(denorm.get("device_screen_resolution_width") or 0)
    height = int(denorm.get("device_screen_resolution_height") or 0)
    return f"{platform}|{width}x{height}"


def _is_recorded(value):
    """True if `value` represents real recorded data, not an unset default.

    Numeric fields default to 0 and string fields to "" when never set, so
    both must be treated as "no data" — checking truthiness on the
    *stringified* value would be wrong here (`str(0.0)` is a non-empty,
    truthy string).
    """
    return value not in (None, "", 0)


_DISPLAY_KEYS = (
    "device_screen_resolution_width", "device_screen_resolution_height",
    "device_screen_resolution_pixel_depth", "device_screen_resolution_color_depth",
)
_CAPACITY_KEYS = ("device_cpu_count", "device_memory")
FUZZY_MATCH_CONFIDENCE = 0.95


def _identifier(value):
    normalized = " ".join(str(value or "").split()).casefold()
    if normalized in {"", "error", "init", "na", "skipped", "unknown", "generic"}:
        return ""
    return normalized


def _renderer(value):
    normalized = _identifier(value)
    if any(marker in normalized for marker in (
        "swiftshader", "llvmpipe", "softpipe", "software", "lavapipe",
    )):
        return ""
    hardware_name = normalized.replace("(tm)", "").replace("(r)", "")
    hardware_name = " ".join(hardware_name.split())
    if not re.search(
        r"(?:geforce\s+(?:rtx|gtx|gt|mx)\s*\d|quadro\s+(?:rtx\s*)?[pkm]?\d|"
        r"radeon\s+(?:rx|hd|pro|vega|r[579])\s*\w*\d|adreno\s+\d|"
        r"mali[-\s]+[gt]\d|powervr\s+\w*\d|apple\s+m\d|"
        r"(?:hd|uhd|iris(?:\s+(?:pro|plus))?)\s+graphics\s+\d)",
        hardware_name,
    ):
        return ""
    return normalized


def _model(value):
    normalized = _identifier(value)
    return normalized if re.search(r"\d", normalized) else ""


def _positive_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _platform_family(value):
    platform = _identifier(value)
    if platform.startswith("win"):
        return "windows"
    if platform.startswith("mac"):
        return "macos"
    if platform.startswith("linux"):
        return "linux"
    return platform


def assess_match(device, denorm):
    """Assess three required groups against one immutable creation profile."""
    profile = getattr(device, "match_profile", None) or {}
    matched, missing, conflicts = [], [], []
    if not profile:
        return {"eligible": False, "matched_groups": [],
                "missing_groups": ["graphics_model", "display", "capacity"],
                "conflicts": [], "reason": "no_trusted_profile"}

    identifiers_match = False
    for key, normalize in (
        ("graphics_web_gl_renderer", _renderer),
        ("browser_high_entropy_values_model", _model),
    ):
        prior, incoming = normalize(profile.get(key)), normalize(denorm.get(key))
        if prior and incoming:
            if prior == incoming:
                identifiers_match = True
            else:
                conflicts.append(key)
    (matched if identifiers_match else missing).append("graphics_model")

    uncertain = _is_firefox(profile) or _is_firefox(denorm)
    for group, keys in (("display", _DISPLAY_KEYS), ("capacity", _CAPACITY_KEYS)):
        prior = tuple(_positive_number(profile.get(key)) for key in keys)
        incoming = tuple(_positive_number(denorm.get(key)) for key in keys)
        if uncertain or None in prior or None in incoming:
            missing.append(group)
        elif prior == incoming:
            matched.append(group)
        else:
            conflicts.append(group)

    for key, normalize in (
        ("device_platform", _platform_family),
        ("browser_high_entropy_values_platform", _identifier),
        ("browser_high_entropy_values_architecture", _identifier),
        ("browser_high_entropy_values_bitness", _identifier),
    ):
        prior, incoming = normalize(profile.get(key)), normalize(denorm.get(key))
        if prior and incoming and prior != incoming:
            conflicts.append(key)
    for reading in (profile, denorm):
        platform = _identifier(reading.get("device_platform"))
        architecture = _identifier(reading.get("browser_high_entropy_values_architecture"))
        if (("arm" in platform or "aarch64" in platform) and architecture.startswith("x86")) or (
            "x86" in platform and architecture.startswith("arm")
        ):
            conflicts.append("inconsistent_platform_architecture")
            break
    return {"eligible": len(matched) == 3 and not conflicts,
            "matched_groups": matched, "missing_groups": missing,
            "conflicts": conflicts}


def score_match(device, denorm, client_ip=None):
    """Compatibility score; IP and generic agreement cannot establish identity."""
    return FUZZY_MATCH_CONFIDENCE if assess_match(device, denorm)["eligible"] else 0.0


def _apply_canonical_fields(device, denorm):
    """Most-recent-write-wins: only overwrite with non-empty, trustworthy incoming values."""
    skip_fields = _volatile_fields_for(denorm)
    for attr, key in CANONICAL_FIELDS:
        if attr in skip_fields:
            continue
        value = denorm.get(key)
        if _is_recorded(value):
            setattr(device, attr, value)


def _record_ip(device, client_ip):
    if not client_ip:
        return
    ips = list(device.recent_ips or [])
    if client_ip in ips:
        ips.remove(client_ip)
    ips.append(client_ip)
    device.recent_ips = ips[-MAX_RECENT_IPS:]


def _record_cookie(device, cookie_id, timestamp, confidence, method, evidence):
    if not cookie_id:
        return
    link = DeviceCookie.query.filter_by(cookie_id=cookie_id).first()
    if link is None:
        link = DeviceCookie(
            device_id=device.id, cookie_id=cookie_id, first_seen=timestamp,
            match_confidence=confidence, match_method=method, match_evidence=evidence,
        )
        db.session.add(link)
    link.last_seen = timestamp


def _best_of(candidates, denorm, client_ip):
    eligible = []
    for candidate in candidates:
        score = score_match(candidate, denorm, client_ip)
        if score:
            eligible.append((candidate, score))
    return eligible[0] if len(eligible) == 1 else (None, 0.0)


def resolve_device(denorm, client_ip=None, cookie_id=None, timestamp=0):
    """Find-or-create the Device this fingerprint belongs to.

    Returns (device, confidence).
    """
    device = None
    confidence = 1.0
    method = "created"
    evidence = {}

    if cookie_id:
        cookie_link = DeviceCookie.query.filter_by(cookie_id=cookie_id).first()
        if cookie_link is not None:
            device = cookie_link.device
            confidence = cookie_link.match_confidence
            if confidence is None:
                confidence = device.confidence
            method = "uuid"
        else:
            device = Device.query.filter_by(cookie_id=cookie_id).first()
            if device is not None:
                confidence = device.confidence
                method = "uuid"

    if device is None:
        incoming_profile = SimpleNamespace(match_profile=denorm)
        if assess_match(incoming_profile, denorm)["eligible"]:
            filters = {attr: denorm[key] for attr, key in CANONICAL_FIELDS
                       if key in _DISPLAY_KEYS + _CAPACITY_KEYS}
            candidates = Device.query.filter_by(**filters).all()
            device, confidence = _best_of(candidates, denorm, client_ip)
            if device is not None:
                method = "fuzzy"
                evidence = assess_match(device, denorm)

    if device is None:
        device = Device(device_bucket=make_bucket(denorm), first_seen=timestamp)
        confidence = 1.0
        device.match_profile = {
            key: denorm.get(key) for _attr, key in CANONICAL_FIELDS
        }
        device.match_profile["browser_user_agent"] = denorm.get("browser_user_agent", "")
        _apply_canonical_fields(device, denorm)
        db.session.add(device)
        db.session.flush()

    if method == "uuid":
        evidence = assess_match(device, denorm)
        if evidence["conflicts"]:
            logger.warning("Device %s UUID reading conflicts with creation profile: %s",
                           device.id, evidence["conflicts"])

    if cookie_id and not device.cookie_id:
        device.cookie_id = cookie_id

    _record_ip(device, client_ip)
    _record_cookie(device, cookie_id, timestamp, confidence, method, evidence)
    device.last_seen = timestamp
    device.confidence = confidence

    is_mobile, dtype = derive_device_type(denorm)
    if dtype != "unknown":
        device.is_mobile = is_mobile
        device.device_type = dtype

    return device, confidence

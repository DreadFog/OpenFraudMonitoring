"""
Device matching — fuzzy, weighted resolution of a Device identity cluster.

Unlike `Session.fsid` (exact match, but volatile: FPScanner bakes the canvas
fingerprint into the hash that produces `fsid`, so canvas randomization alone
creates what looks like a brand-new session), a Device is resolved by scoring
how many *stable* hardware/OS signals agree with a previously-seen device.

Resolution order (highest confidence first):
  1. Client-side device UUID cookie — exact match, confidence 1.0.
  2. Weighted field-similarity score against candidates sharing a coarse
     "bucket" (platform + screen resolution), boosted slightly by recent
     IP/subnet proximity. Above `DEVICE_MATCH_THRESHOLD` → link.
  3. No match → create a new Device.

See docs/devices.md for the full rationale and field tiering.
"""

import ipaddress

from flask import current_app

from services.database import db
from models.device import Device, DeviceCookie, MAX_RECENT_IPS

# ── Field tiers ──
# (device attribute, denormalized Fingerprint column, weight)
# Tier A — hardware-bound, weighted higher (rarely changes for a real device).
_TIER_A_FIELDS = [
    ("platform", "device_platform", 3),
    ("screen_width", "device_screen_resolution_width", 2),
    ("screen_height", "device_screen_resolution_height", 2),
    ("pixel_depth", "device_screen_resolution_pixel_depth", 1),
    ("color_depth", "device_screen_resolution_color_depth", 1),
    ("speakers", "device_multimedia_devices_speakers", 1),
    ("microphones", "device_multimedia_devices_microphones", 1),
    ("webcams", "device_multimedia_devices_webcams", 1),
    ("webgl_vendor", "graphics_web_gl_vendor", 2),
    ("webgl_renderer", "graphics_web_gl_renderer", 3),
    ("hev_architecture", "browser_high_entropy_values_architecture", 2),
    ("hev_bitness", "browser_high_entropy_values_bitness", 2),
    ("hev_model", "browser_high_entropy_values_model", 2),
]

# Tier B — OS/browser-bound, low weight; mostly useful as tie-breakers.
_TIER_B_FIELDS = [
    ("hev_platform", "browser_high_entropy_values_platform", 1),
    ("hev_platform_version", "browser_high_entropy_values_platform_version", 1),
    ("timezone", "locale_internationalization_timezone", 1),
    ("language", "locale_languages_language", 1),
    ("audio_codec_hash", "codecs_audio_can_play_type_hash", 1),
    ("video_codec_hash", "codecs_video_can_play_type_hash", 1),
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

# IP/subnet proximity contributes a small, capped boost — it can nudge a
# borderline match but can never single-handedly cause one.
IP_PROXIMITY_BOOST = 0.05

# When the bucket prefilter finds nothing (e.g. the same device seen through a
# different browser, landing in a different bucket scheme), fall back to a
# bounded platform-only scan instead of giving up and creating a duplicate.
FALLBACK_SCAN_LIMIT = 200

# Avoid high-confidence matches from very sparse readings (e.g. platform only).
MIN_MATCH_EVIDENCE_WEIGHT = 8


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
    """Coarse prefilter key so we don't score every Device row on each request."""
    platform = _norm(denorm.get("device_platform")) or "unknown"
    if _is_firefox(denorm):
        # Screen dims are RFP-spoofed and drift with window size — fall back
        # to GPU renderer for a bucket key that isn't tied to window state.
        renderer = _norm(denorm.get("graphics_web_gl_renderer")) or "unknown-gpu"
        return f"{platform}|firefox-rfp|{renderer}"
    width = int(denorm.get("device_screen_resolution_width") or 0)
    height = int(denorm.get("device_screen_resolution_height") or 0)
    return f"{platform}|{width}x{height}"


def _subnet_key(ip):
    """Return a /24 for IPv4 (proximity-tolerant) or the exact address for IPv6."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if addr.version == 4:
        return str(ipaddress.ip_network(f"{ip}/24", strict=False))
    return str(addr)


def _has_ip_proximity(device, client_ip):
    if not client_ip:
        return False
    key = _subnet_key(client_ip)
    if not key:
        return False
    return any(_subnet_key(ip) == key for ip in (device.recent_ips or []))


def _is_recorded(value):
    """True if `value` represents real recorded data, not an unset default.

    Numeric fields default to 0 and string fields to "" when never set, so
    both must be treated as "no data" — checking truthiness on the
    *stringified* value would be wrong here (`str(0.0)` is a non-empty,
    truthy string).
    """
    return value not in (None, "", 0)


def score_match(device, denorm, client_ip=None):
    """Weighted field-agreement score in [0, 1].

    Only fields recorded on both sides are scored. Missing browser-specific
    signals (e.g. Firefox omitting UA-CH/WebGL details) are absence of evidence,
    not mismatches.
    """
    skip_fields = _volatile_fields_for(denorm)
    matched_weight = 0.0
    total_weight = 0.0
    for attr, key, weight in CANONICAL_FIELDS:
        if attr in skip_fields:
            continue
        raw_value = getattr(device, attr, None)
        incoming_value = denorm.get(key)
        if not _is_recorded(raw_value) or not _is_recorded(incoming_value):
            continue
        total_weight += weight
        if _norm(raw_value) == _norm(incoming_value):
            matched_weight += weight

    if total_weight < MIN_MATCH_EVIDENCE_WEIGHT:
        return 0.0

    score = matched_weight / total_weight
    if _has_ip_proximity(device, client_ip):
        score = min(1.0, score + IP_PROXIMITY_BOOST)
    return score


def _apply_canonical_fields(device, denorm):
    """Most-recent-write-wins: only overwrite with non-empty, trustworthy incoming values."""
    skip_fields = _volatile_fields_for(denorm)
    for attr, key, _weight in CANONICAL_FIELDS:
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


def _record_cookie(device, cookie_id, timestamp):
    if not cookie_id:
        return
    link = DeviceCookie.query.filter_by(cookie_id=cookie_id).first()
    if link is None:
        link = DeviceCookie(device_id=device.id, cookie_id=cookie_id, first_seen=timestamp)
        db.session.add(link)
    link.device_id = device.id
    link.last_seen = timestamp


def _best_of(candidates, denorm, client_ip):
    best, best_score = None, 0.0
    for candidate in candidates:
        score = score_match(candidate, denorm, client_ip)
        if score > best_score:
            best, best_score = candidate, score
    return best, best_score


def resolve_device(denorm, client_ip=None, cookie_id=None, timestamp=0):
    """Find-or-create the Device this fingerprint belongs to.

    Returns (device, confidence).
    """
    device = None
    confidence = 1.0

    if cookie_id:
        cookie_link = DeviceCookie.query.filter_by(cookie_id=cookie_id).first()
        if cookie_link is not None:
            device = cookie_link.device
        else:
            device = Device.query.filter_by(cookie_id=cookie_id).first()

    if device is None:
        bucket = make_bucket(denorm)
        candidates = Device.query.filter_by(device_bucket=bucket).all()
        best, best_score = _best_of(candidates, denorm, client_ip)

        if best is None:
            # No candidates in this bucket at all — possibly the same device
            # seen through a different browser (different bucket scheme, e.g.
            # Firefox RFP vs. a real resolution). Broaden the search instead
            # of immediately creating a duplicate Device.
            platform = _norm(denorm.get("device_platform"))
            if platform:
                fallback_candidates = (
                    Device.query.filter_by(platform=platform)
                    .order_by(Device.last_seen.desc())
                    .limit(FALLBACK_SCAN_LIMIT)
                    .all()
                )
                best, best_score = _best_of(fallback_candidates, denorm, client_ip)

        threshold = current_app.config.get("DEVICE_MATCH_THRESHOLD", 0.75)
        if best is not None and best_score >= threshold:
            device, confidence = best, best_score

    if device is None:
        device = Device(device_bucket=make_bucket(denorm), first_seen=timestamp)
        confidence = 1.0

    if cookie_id and not device.cookie_id:
        device.cookie_id = cookie_id

    _apply_canonical_fields(device, denorm)
    _record_ip(device, client_ip)
    _record_cookie(device, cookie_id, timestamp)
    device.last_seen = timestamp
    device.confidence = confidence

    is_mobile, dtype = derive_device_type(denorm)
    if dtype != "unknown":
        device.is_mobile = is_mobile
        device.device_type = dtype

    return device, confidence

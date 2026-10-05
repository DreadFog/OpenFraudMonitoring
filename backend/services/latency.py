"""Validate untrusted client timings and attach the configured server context."""

import math
from datetime import datetime, timezone

from services.settings import (
    GLOBAL_DEFAULTS, SERVER_LOCATION_KEY, SERVER_TIMEZONE_KEY, get_global_setting,
)


def normalize_latency(value):
    if not isinstance(value, dict):
        return None
    round_trip = value.get("round_trip_ms")
    measured_at = value.get("measured_at")
    for number, maximum in ((round_trip, 60000), (measured_at, 8640000000000000)):
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            return None
        if not 0 <= number <= maximum or not math.isfinite(number):
            return None
    request_path = value.get("request_path")
    if not isinstance(request_path, str) or not request_path.startswith("/") or len(request_path) > 512:
        return None
    client_timezone = value.get("client_timezone")
    if client_timezone is not None and (not isinstance(client_timezone, str) or len(client_timezone) > 128):
        return None
    offset = value.get("client_utc_offset_minutes")
    if isinstance(offset, bool) or not isinstance(offset, int) or not -1440 <= offset <= 1440:
        return None
    return {
        "round_trip_ms": round_trip,
        "measured_at": measured_at,
        "request_path": request_path,
        "client_timezone": client_timezone,
        "client_utc_offset_minutes": offset,
        "source": "client_reported",
        "measurement": "fetch_response_headers",
        "received_at": datetime.now(timezone.utc).isoformat(),
        "server": {
            "location": get_global_setting(SERVER_LOCATION_KEY) or GLOBAL_DEFAULTS[SERVER_LOCATION_KEY],
            "timezone": get_global_setting(SERVER_TIMEZONE_KEY) or GLOBAL_DEFAULTS[SERVER_TIMEZONE_KEY],
        },
    }


def capture_latency(session, extensions):
    sample = normalize_latency(extensions.get("latency") if isinstance(extensions, dict) else None)
    if sample is not None:
        session.latency = sample
    return sample
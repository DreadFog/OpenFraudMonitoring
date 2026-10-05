let latest = null;

function snapshot() {
  if (!latest) return null;
  let timezone = null;
  try {
    timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch (_) {}
  return {
    ...latest,
    client_timezone: timezone,
    client_utc_offset_minutes: -new Date().getTimezoneOffset(),
  };
}

export default {
  name: "latency",
  collect: snapshot,
  drain: snapshot,
  recordResponse(endpoint, roundTripMs) {
    if (!Number.isFinite(roundTripMs) || roundTripMs < 0) return;
    latest = {
      round_trip_ms: Math.round(roundTripMs * 1000) / 1000,
      measured_at: Date.now(),
      request_path: new URL(endpoint, location.href).pathname,
    };
  },
};
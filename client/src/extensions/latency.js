import { CFG } from "../config.js";

let latest = null;
let pending = null;

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

async function requestProbe(measure) {
  if (document.visibilityState === "hidden" || typeof fetch !== "function") return false;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  const started = performance.now();
  try {
    const response = await fetch(CFG.latencyEndpoint, {
      method: "GET",
      cache: "no-store",
      credentials: "omit",
      signal: controller.signal,
    });
    if (response.status !== 204 || response.headers.get("X-OFM-Latency-Probe") !== "1") return false;
    if (measure && document.visibilityState !== "hidden") {
      const roundTripMs = performance.now() - started;
      if (!Number.isFinite(roundTripMs) || roundTripMs < 0) return false;
      latest = {
        round_trip_ms: Math.round(roundTripMs * 1000) / 1000,
        measured_at: Date.now(),
        request_path: new URL(CFG.latencyEndpoint, location.href).pathname,
        measurement: "lightweight_probe",
      };
    }
    return true;
  } catch (_) {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

function probe() {
  if (pending) return pending;
  if (document.visibilityState === "hidden" || typeof fetch !== "function") return Promise.resolve(snapshot());
  pending = (async () => {
    if (await requestProbe(false)) await requestProbe(true);
    return snapshot();
  })().finally(() => { pending = null; });
  return pending;
}

export default {
  name: "latency",
  snapshot,
  probe,
  async collect() {
    await probe();
    return snapshot();
  },
  drain() {
    void probe();
    return snapshot();
  },
};
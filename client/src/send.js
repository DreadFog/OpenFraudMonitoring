import latency from "./extensions/latency.js";

export function send(endpoint, payload) {
  const body = JSON.stringify({
    ...payload,
    extensions: { ...payload.extensions, latency: latency.collect() },
  });
  if ((document.visibilityState === "hidden" || typeof fetch !== "function") && navigator.sendBeacon) {
    if (navigator.sendBeacon(endpoint, new Blob([body], { type: "application/json" }))) {
      return Promise.resolve(null);
    }
  }
  if (typeof fetch !== "function") return Promise.resolve(null);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  const started = performance.now();
  return fetch(endpoint, {
    method: "POST",
    body,
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    keepalive: true,
    signal: controller.signal,
  })
    .then((response) => {
      if (response.ok) latency.recordResponse(endpoint, performance.now() - started);
      return response;
    })
    .catch(() => null)
    .finally(() => clearTimeout(timeout));
}

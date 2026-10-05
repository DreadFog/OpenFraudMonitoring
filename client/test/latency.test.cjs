const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

async function setup(serverUrl = "") {
  let clock = 100;
  const requests = [];
  const beacons = [];
  const timers = new Set();
  let probeCount = 0;
  const context = vm.createContext({
    Date, Intl, URL, Blob, Promise, AbortController,
    __OFM_SERVER_URL__: serverUrl,
    location: { href: "https://example.test/page" },
    document: { visibilityState: "visible" },
    navigator: { sendBeacon: (endpoint, body) => { beacons.push({ endpoint, body }); return true; } },
    performance: { now: () => clock },
    setTimeout: (callback) => { timers.add(callback); return callback; },
    clearTimeout: (callback) => timers.delete(callback),
    fetch: async (endpoint, options) => {
      requests.push({ endpoint, body: options.body ? JSON.parse(options.body) : null, options });
      if (options.method === "GET") {
        probeCount += 1;
        clock += probeCount % 2 === 1 ? 100 : 5;
        return { ok: true, status: 204, headers: { get: () => "1" } };
      }
      clock += 250;
      return { ok: true, status: 200 };
    },
  });
  const latency = new vm.SourceTextModule(fs.readFileSync(path.join(__dirname, "../src/extensions/latency.js"), "utf8"), { context });
  const config = new vm.SourceTextModule(fs.readFileSync(path.join(__dirname, "../src/config.js"), "utf8"), { context });
  const sender = new vm.SourceTextModule(fs.readFileSync(path.join(__dirname, "../src/send.js"), "utf8"), { context });
  await config.link(() => {});
  await latency.link(() => config);
  await sender.link(() => latency);
  await sender.evaluate();
  return { context, requests, beacons, timers, send: sender.namespace.send, latency: latency.namespace.default };
}

test("warm-up is discarded and only the second sequential probe is measured", async () => {
  const { send, latency, requests, timers } = await setup();
  const sample = await latency.collect();
  assert.equal(requests.length, 2);
  assert.equal(sample.round_trip_ms, 5);
  assert.equal(sample.request_path, "/api/latency");
  assert.equal(sample.measurement, "lightweight_probe");
  assert.equal(typeof sample.client_timezone, "string");
  for (const request of requests) {
    assert.equal(request.options.method, "GET");
    assert.equal(request.options.credentials, "omit");
    assert.equal(request.options.cache, "no-store");
  }
  await send("/api/initial", { visit_id: "visit", extensions: { device_id: { uuid: "device" } } });
  assert.equal(requests[2].body.extensions.device_id.uuid, "device");
  assert.equal(requests[2].body.extensions.latency.round_trip_ms, 5);
  assert.equal(requests[2].options.credentials, "include");
  assert.equal(timers.size, 0);
});

test("slow ingestion requests carry but never overwrite the probe timing", async () => {
  const { send, latency, requests } = await setup();
  await latency.probe();
  await send("/api/behavioral_event", { event_type: "button_click", data: { text: "Save" } });
  await send("/api/heartbeat", { extensions: { behavior: { clicks: [] } } });
  assert.equal(requests[2].body.extensions.latency.round_trip_ms, 5);
  assert.equal(requests[2].body.data.text, "Save");
  assert.equal(requests[3].body.extensions.latency.round_trip_ms, 5);
  assert.equal(latency.snapshot().round_trip_ms, 5);
});

test("heartbeat drain returns the previous sample while refreshing the next one", async () => {
  const { latency, requests } = await setup();
  await latency.probe();
  assert.equal(latency.drain().round_trip_ms, 5);
  await latency.probe();
  assert.equal(requests.length, 4);
  assert.equal(latency.snapshot().round_trip_ms, 5);
});

test("failed and non-probe responses do not replace a good sample", async () => {
  const { context, latency, timers } = await setup();
  await latency.probe();
  context.fetch = async () => ({ status: 200, headers: { get: () => "1" } });
  await latency.probe();
  context.fetch = async () => ({ status: 204, headers: { get: () => null } });
  await latency.probe();
  context.fetch = async () => { throw new Error("Network failure"); };
  await latency.probe();
  assert.equal(latency.snapshot().request_path, "/api/latency");
  assert.equal(latency.snapshot().round_trip_ms, 5);
  assert.equal(timers.size, 0);
});

test("hidden pages skip probes and beacon delivery carries the last valid sample", async () => {
  const { send, context, requests, beacons, latency } = await setup();
  await latency.probe();
  context.document.visibilityState = "hidden";
  await latency.probe();
  latency.drain();
  await send("/api/heartbeat", {});
  assert.equal(requests.length, 2);
  assert.equal(JSON.parse(await beacons[0].body.text()).extensions.latency.round_trip_ms, 5);
  assert.equal(latency.snapshot().request_path, "/api/latency");
});

test("rejected beacon falls back to collection fetch without fabricating a timing", async () => {
  const { send, context, requests, latency } = await setup();
  context.document.visibilityState = "hidden";
  context.navigator.sendBeacon = () => false;
  await send("/api/heartbeat", {});
  assert.equal(requests.length, 1);
  assert.equal(latency.snapshot(), null);
});

test("probe timeout aborts fetch and never records a fabricated sample", async () => {
  const { context, timers, latency } = await setup();
  context.fetch = (endpoint, options) => new Promise((resolve, reject) => {
    options.signal.addEventListener("abort", () => reject(new Error("Aborted")));
  });
  const pending = latency.probe();
  for (const callback of timers) callback();
  assert.equal(await pending, null);
  assert.equal(latency.snapshot(), null);
  assert.equal(timers.size, 0);
});

test("concurrent refreshes share one sequential probe pair", async () => {
  const { latency, requests } = await setup();
  const first = latency.probe();
  const second = latency.probe();
  assert.equal(first, second);
  await first;
  assert.equal(requests.length, 2);
});

test("a page hidden during the measured request does not publish a new sample", async () => {
  const { context, latency } = await setup();
  let count = 0;
  context.fetch = async () => {
    count += 1;
    if (count === 2) context.document.visibilityState = "hidden";
    return { status: 204, headers: { get: () => "1" } };
  };
  assert.equal(await latency.collect(), null);
});

test("configured collection origins and path prefixes also apply to the probe", async () => {
  const { latency, requests } = await setup("https://collector.test/ofm");
  await latency.probe();
  assert.equal(requests[0].endpoint, "https://collector.test/ofm/api/latency");
  assert.equal(latency.snapshot().request_path, "/ofm/api/latency");
});
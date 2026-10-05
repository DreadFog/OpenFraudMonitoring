const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

async function setup() {
  let clock = 100;
  const requests = [];
  const beacons = [];
  const timers = new Set();
  const context = vm.createContext({
    Date, Intl, URL, Blob, Promise, AbortController,
    location: { href: "https://example.test/page" },
    document: { visibilityState: "visible" },
    navigator: { sendBeacon: (endpoint, body) => { beacons.push({ endpoint, body }); return true; } },
    performance: { now: () => clock },
    setTimeout: (callback) => { timers.add(callback); return callback; },
    clearTimeout: (callback) => timers.delete(callback),
    fetch: async (endpoint, options) => {
      requests.push({ endpoint, body: JSON.parse(options.body), options });
      clock += 25;
      return { ok: true };
    },
  });
  const latency = new vm.SourceTextModule(fs.readFileSync(path.join(__dirname, "../src/extensions/latency.js"), "utf8"), { context });
  const sender = new vm.SourceTextModule(fs.readFileSync(path.join(__dirname, "../src/send.js"), "utf8"), { context });
  await latency.link(() => {});
  await sender.link(() => latency);
  await sender.evaluate();
  return { context, requests, beacons, timers, send: sender.namespace.send, latency: latency.namespace.default };
}

test("next request reports the prior successful response, preserving extension data", async () => {
  const { send, requests, timers } = await setup();
  await send("/api/initial", { visit_id: "visit", extensions: { device_id: { uuid: "device" } } });
  await send("/api/heartbeat", { visit_id: "visit", extensions: { behavior: { clicks: [] } } });
  assert.equal(requests[0].body.extensions.latency, null);
  assert.equal(requests[0].body.extensions.device_id.uuid, "device");
  assert.equal(requests[1].body.extensions.latency.round_trip_ms, 25);
  assert.equal(requests[1].body.extensions.latency.request_path, "/api/initial");
  assert.equal(typeof requests[1].body.extensions.latency.client_timezone, "string");
  assert.equal(requests[1].options.credentials, "include");
  assert.equal(timers.size, 0);
});

test("behavior requests also carry the previous timing", async () => {
  const { send, requests } = await setup();
  await send("/api/initial", {});
  await send("/api/behavioral_event", { event_type: "button_click", data: { text: "Save" } });
  assert.equal(requests[1].body.extensions.latency.round_trip_ms, 25);
  assert.equal(requests[1].body.data.text, "Save");
});

test("failed and non-successful responses do not replace a good sample", async () => {
  const { send, context, latency, timers } = await setup();
  await send("/api/initial", {});
  context.fetch = async () => ({ ok: false });
  await send("/api/heartbeat", {});
  context.fetch = async () => { throw new Error("Network failure"); };
  await send("/api/heartbeat", {});
  assert.equal(latency.drain().request_path, "/api/initial");
  assert.equal(latency.drain().round_trip_ms, 25);
  assert.equal(timers.size, 0);
});

test("hidden-page beacon carries the previous sample without recording a new one", async () => {
  const { send, context, requests, beacons, latency } = await setup();
  await send("/api/initial", {});
  context.document.visibilityState = "hidden";
  await send("/api/heartbeat", {});
  assert.equal(requests.length, 1);
  assert.equal(JSON.parse(await beacons[0].body.text()).extensions.latency.round_trip_ms, 25);
  assert.equal(latency.drain().request_path, "/api/initial");
});

test("rejected beacon falls back to measurable fetch", async () => {
  const { send, context, requests, latency } = await setup();
  context.document.visibilityState = "hidden";
  context.navigator.sendBeacon = () => false;
  await send("/api/heartbeat", {});
  assert.equal(requests.length, 1);
  assert.equal(latency.drain().round_trip_ms, 25);
});

test("timeout aborts fetch and never records a fabricated sample", async () => {
  const { send, context, timers, latency } = await setup();
  context.fetch = (endpoint, options) => new Promise((resolve, reject) => {
    options.signal.addEventListener("abort", () => reject(new Error("Aborted")));
  });
  const pending = send("/api/initial", {});
  for (const callback of timers) callback();
  assert.equal(await pending, null);
  assert.equal(latency.collect(), null);
  assert.equal(timers.size, 0);
});

test("invalid durations are ignored and paths never retain query strings", async () => {
  const { latency } = await setup();
  latency.recordResponse("/api/initial?token=private", 10.12345);
  latency.recordResponse("/api/heartbeat", -1);
  latency.recordResponse("/api/heartbeat", Infinity);
  assert.equal(latency.collect().round_trip_ms, 10.123);
  assert.equal(latency.collect().request_path, "/api/initial");
});
/**
 * OFM Client — wraps FPScanner with extensible custom collectors.
 *
 * Flow:
 *   1. Init all extensions (attach event listeners, etc.)
 *   2. Collect FPScanner fingerprint and encrypt that snapshot
 *   3. Run each extension's collect() in parallel
 *   4. Send combined payload to /api/initial
 *   5. Start heartbeat loop (drains extension buffers periodically)
 */

import FingerprintScanner from "fpscanner";
import { CFG } from "./config.js";
import { send } from "./send.js";
import extensions from "./extensions/index.js";
import { generateUuid } from "./uuid.js";

const VISIT_STORAGE_KEY = "ofm_visit_id";

function getVisitId() {
  try {
    const existing = sessionStorage.getItem(VISIT_STORAGE_KEY);
    if (existing) return existing;
    const visitId = generateUuid();
    sessionStorage.setItem(VISIT_STORAGE_KEY, visitId);
    return visitId;
  } catch (_) {
    return generateUuid();
  }
}

// sessionStorage survives reloads in this tab and is cleared when the tab closes.
const _visitId = getVisitId();

// ── Global hooks for debugging / demo pages (debug builds only) ──
if (__OFM_DEBUG__) {
  if (typeof window !== "undefined" && !window.__OFM__) {
    window.__OFM__ = {};
  }
}

// ── Helpers ──

function initExtensions() {
  for (const ext of extensions) {
    if (typeof ext.init === "function") {
      try { ext.init(); } catch (e) { console.warn(`[OFM] extension ${ext.name} init failed:`, e); }
    }
  }
}

async function collectExtensions() {
  const results = {};
  const promises = extensions
    .filter(ext => typeof ext.collect === "function")
    .map(async (ext) => {
      try {
        results[ext.name] = await ext.collect();
      } catch (e) {
        console.warn(`[OFM] extension ${ext.name} collect failed:`, e);
        results[ext.name] = null;
      }
    });
  await Promise.all(promises);
  return results;
}

function drainExtensions() {
  const results = {};
  for (const ext of extensions) {
    if (typeof ext.drain === "function") {
      try {
        results[ext.name] = ext.drain();
      } catch (e) {
        console.warn(`[OFM] extension ${ext.name} drain failed:`, e);
      }
    }
  }
  return results;
}

// ── Collection ──

async function collect() {
  const scanner = new FingerprintScanner();
  const debugFingerprintHook = __OFM_DEBUG__ && typeof window !== "undefined" &&
    window.__OFM__ && typeof window.__OFM__.onFingerprint === "function";

  const [fingerprint, extensionData] = await Promise.all([
    scanner.collectFingerprint({ encrypt: !debugFingerprintHook }),
    collectExtensions(),
  ]);

  const fp = debugFingerprintHook ? fingerprint : null;
  const encrypted = debugFingerprintHook
    ? await scanner.collectFingerprint({ encrypt: true })
    : fingerprint;

  const payload = {
    fingerprint: encrypted,     // FPScanner encrypted payload
    visit_id: _visitId,
    extensions: extensionData,  // { ip: {...}, ... }
    timestamp: Date.now(),
    url: location.href,
  };

  // Expose unencrypted payload for demo/debug (debug builds only)
  if (debugFingerprintHook) {
    try { window.__OFM__.onFingerprint({ ...fp, _extensions: extensionData }); } catch (_) {}
  }

  await send(CFG.collectEndpoint, payload);
}

// ── Heartbeat ──

function startHeartbeat() {
  function beat() {
    const snapshot = {
      visit_id: _visitId,
      timestamp: Date.now(),
      url: location.href,
      extensions: drainExtensions(),  // { behavior: { mouseMoves: [...], ... } }
    };

    // Expose heartbeat payload for demo/debug (debug builds only)
    if (__OFM_DEBUG__ && window.__OFM__ && typeof window.__OFM__.onHeartbeat === "function") {
      try { window.__OFM__.onHeartbeat(snapshot); } catch (_) {}
    }

    send(CFG.heartbeatEndpoint, snapshot);
  }

  beat();
  setInterval(beat, CFG.heartbeatMs);
}

// ── Init ──

function init() {
  initExtensions();
  const behaviorExt = extensions.find(ext => ext.name === "behavior");
  if (behaviorExt && typeof behaviorExt.setVisitId === "function") {
    behaviorExt.setVisitId(_visitId);
  }
  collect().then(startHeartbeat);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

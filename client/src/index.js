/**
 * OFM Client — wraps FPScanner with extensible custom collectors.
 *
 * Flow:
 *   1. Init all extensions (attach event listeners, etc.)
 *   2. Collect FPScanner fingerprint (encrypted)
 *   3. Run each extension's collect() in parallel
 *   4. Send combined payload to /api/initial
 *   5. Start heartbeat loop (drains extension buffers periodically)
 */

import FingerprintScanner from "fpscanner";
import { CFG } from "./config.js";
import { send } from "./send.js";
import extensions from "./extensions/index.js";

// Cached fsid for heartbeat correlation (set after first collect)
let _fsid = null;

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

  // Run FPScanner + extensions in parallel
  // Collect unencrypted to extract fsid for heartbeat correlation,
  // then encrypt the same fingerprint for transmission
  const [fp, extensionData] = await Promise.all([
    scanner.collectFingerprint({ encrypt: false }),
    collectExtensions(),
  ]);

  _fsid = fp.fsid;

  // Re-encrypt for transmission (fast — just XOR + base64)
  const encrypted = await scanner.collectFingerprint({ encrypt: true });

  const payload = {
    fingerprint: encrypted,     // FPScanner encrypted payload
    extensions: extensionData,  // { ip: {...}, ... }
    timestamp: Date.now(),
    url: location.href,
  };

  // Expose unencrypted payload for demo/debug (debug builds only)
  if (__OFM_DEBUG__ && window.__OFM__ && typeof window.__OFM__.onFingerprint === "function") {
    try { window.__OFM__.onFingerprint({ ...fp, _extensions: extensionData }); } catch (_) {}
  }

  send(CFG.collectEndpoint, payload);
}

// ── Heartbeat ──

function startHeartbeat() {
  function beat() {
    const snapshot = {
      fsid: _fsid,
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
  collect().then(() => startHeartbeat());
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

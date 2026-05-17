/**
 * Behavior Extension — tracks user interactions (mouse, keyboard, touch, scroll)
 * and sends high-signal events (button clicks, form submits, copy/paste) directly.
 *
 * Extension interface:
 *   name    – unique identifier
 *   init    – called once at startup to attach event listeners
 *   setFsid – called after collect() resolves to set the session fsid for direct events
 *   drain   – called every heartbeat cycle; returns accumulated low-signal events
 */

import { send } from "../send.js";
import { CFG } from "../config.js";

const MAX_MOUSE   = 300;
const MAX_CLICKS  = 100;
const MAX_KEYS    = 200;
const MAX_TOUCHES = 100;
const MAX_SCROLLS = 100;

const buf = {
  mouseMoves:       [],
  clicks:           [],
  keydowns:         [],
  touches:          [],
  scrolls:          [],
  _lastMouse:       0,
  _lastScroll:      0,
  _fsid:            null,
};

function now() {
  return Date.now();
}

function sendDirect(eventType, data) {
  const payload = {
    fsid: buf._fsid,
    timestamp: now(),
    url: location.href,
    event_type: eventType,
    data,
  };
  send(CFG.behavioralEventEndpoint, payload);
  
  // Debug hook
  if (typeof window !== "undefined" && window.__OFM__ && typeof window.__OFM__.onBehavioralEvent === "function") {
    try { window.__OFM__.onBehavioralEvent(payload); } catch (_) {}
  }
}

export default {
  name: "behavior",

  setFsid(fsid) {
    buf._fsid = fsid;
  },

  init() {
    document.addEventListener("mousemove", (e) => {
      const t = now();
      if (t - buf._lastMouse < 50) return;
      buf._lastMouse = t;
      if (buf.mouseMoves.length < MAX_MOUSE)
        buf.mouseMoves.push([Math.round(e.clientX), Math.round(e.clientY), t]);
    }, { passive: true });

    document.addEventListener("click", (e) => {
      // Button clicks: send directly, do not buffer
      const isButton = e.target.closest("button") || 
                       e.target.closest("[type=submit]") || 
                       e.target.closest("[role=button]");
      if (isButton) {
        sendDirect("button_click", {
          x: Math.round(e.clientX),
          y: Math.round(e.clientY),
          tag: e.target.tagName.toLowerCase(),
          text: (e.target.innerText || e.target.textContent || "").slice(0, 50),
        });
      } else {
        // Non-button clicks: buffer for heartbeat
        if (buf.clicks.length < MAX_CLICKS)
          buf.clicks.push({ x: Math.round(e.clientX), y: Math.round(e.clientY), t: now(), button: e.button });
      }
    }, { passive: true });

    document.addEventListener("keydown", (e) => {
      if (buf.keydowns.length < MAX_KEYS)
        buf.keydowns.push({
          key: e.keyCode,
          t: now(),
          mod: (+e.ctrlKey) | (+e.shiftKey << 1) | (+e.altKey << 2) | (+e.metaKey << 3),
        });
    }, { passive: true });

    document.addEventListener("touchstart", (e) => {
      const t0 = e.touches[0];
      if (buf.touches.length < MAX_TOUCHES && t0)
        buf.touches.push({ x: Math.round(t0.clientX), y: Math.round(t0.clientY), r: t0.radiusX || null, t: now() });
    }, { passive: true });

    window.addEventListener("scroll", () => {
      const t = now();
      if (t - buf._lastScroll < 100) return;
      buf._lastScroll = t;
      if (buf.scrolls.length < MAX_SCROLLS)
        buf.scrolls.push([Math.round(window.scrollX), Math.round(window.scrollY), t]);
    }, { passive: true });

    // Form submit: send directly
    document.addEventListener("submit", (e) => {
      const form = e.target;
      const fields = Array.from(form.querySelectorAll("input, select, textarea"))
        .map(el => ({
          name: el.name || el.id || "",
          type: el.type || "",
          ...(CFG.captureFormValues && { value: el.value || "" }),
        }))
        .filter(f => f.name);
      
      const fieldNames = fields.map(f => f.name);
      const payload = {
        action: form.action || "",
        method: form.method || "POST",
        fieldNames,
      };
      
      if (CFG.captureFormValues) {
        payload.fields = fields;
        console.debug("[OFM] Form submit with captured values:", payload);
      } else {
        console.debug("[OFM] Form submit without captured values (captureFormValues=" + CFG.captureFormValues + ")");
      }
      
      sendDirect("form_submit", payload);
    }, { passive: true });

    // Copy: send directly with length only (no content)
    document.addEventListener("copy", (e) => {
      const text = (e.clipboardData || window.clipboardData || { getData: () => "" }).getData("text");
      sendDirect("copy", { length: text.length });
    }, { passive: true });

    // Paste: send directly with length only (no content)
    document.addEventListener("paste", (e) => {
      const text = (e.clipboardData || window.clipboardData || { getData: () => "" }).getData("text");
      sendDirect("paste", { length: text.length });
    }, { passive: true });
  },

  /**
   * Drain all accumulated low-signal behavior events. Resets buffers atomically.
   * Called by the heartbeat loop. High-signal events are sent directly and not buffered.
   */
  drain() {
    return {
      mouseMoves:       buf.mouseMoves.splice(0),
      clicks:           buf.clicks.splice(0),
      keydowns:         buf.keydowns.splice(0),
      touches:          buf.touches.splice(0),
      scrolls:          buf.scrolls.splice(0),
    };
  },
};

/**
 * Behavior Extension — tracks user interactions (mouse, keyboard, touch,
 * scroll, clipboard, navigation) and provides a drain function for heartbeats.
 *
 * Extension interface:
 *   name  – unique identifier
 *   init  – called once at startup to attach event listeners
 *   drain – called every heartbeat cycle; returns accumulated events and resets buffers
 */

const MAX_MOUSE   = 300;
const MAX_CLICKS  = 100;
const MAX_KEYS    = 200;
const MAX_TOUCHES = 100;
const MAX_SCROLLS = 100;
const MAX_CLIPS   = 50;
const MAX_NAVS    = 50;

const buf = {
  mouseMoves:       [],
  clicks:           [],
  keydowns:         [],
  touches:          [],
  scrolls:          [],
  copyPastes:       [],
  navigationEvents: [],
  _lastMouse:       0,
  _lastScroll:      0,
  _lastURL:         "",
};

function now() {
  return Date.now();
}

function trackNavigation() {
  const url = location.href;
  if (url !== buf._lastURL) {
    if (buf.navigationEvents.length < MAX_NAVS)
      buf.navigationEvents.push({ from: buf._lastURL, to: url, t: now() });
    buf._lastURL = url;
  }
}

export default {
  name: "behavior",

  init() {
    buf._lastURL = location.href;

    document.addEventListener("mousemove", (e) => {
      const t = now();
      if (t - buf._lastMouse < 50) return;
      buf._lastMouse = t;
      if (buf.mouseMoves.length < MAX_MOUSE)
        buf.mouseMoves.push([Math.round(e.clientX), Math.round(e.clientY), t]);
    }, { passive: true });

    document.addEventListener("click", (e) => {
      if (buf.clicks.length < MAX_CLICKS)
        buf.clicks.push({ x: Math.round(e.clientX), y: Math.round(e.clientY), t: now(), button: e.button });
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

    document.addEventListener("copy", (e) => {
      const text = (e.clipboardData || window.clipboardData || { getData: () => "" }).getData("text");
      if (buf.copyPastes.length < MAX_CLIPS)
        buf.copyPastes.push({ type: "copy", content: text.slice(0, 100), t: now() });
    }, { passive: true });

    document.addEventListener("paste", (e) => {
      const text = (e.clipboardData || window.clipboardData || { getData: () => "" }).getData("text");
      if (buf.copyPastes.length < MAX_CLIPS)
        buf.copyPastes.push({ type: "paste", content: text.slice(0, 100), t: now() });
    }, { passive: true });

    window.addEventListener("popstate", trackNavigation);
    setInterval(trackNavigation, 1000);
  },

  /**
   * Drain all accumulated behavior events. Resets buffers atomically.
   * Called by the heartbeat loop.
   */
  drain() {
    trackNavigation();
    return {
      mouseMoves:       buf.mouseMoves.splice(0),
      clicks:           buf.clicks.splice(0),
      keydowns:         buf.keydowns.splice(0),
      touches:          buf.touches.splice(0),
      scrolls:          buf.scrolls.splice(0),
      copyPastes:       buf.copyPastes.splice(0),
      navigationEvents: buf.navigationEvents.splice(0),
    };
  },
};

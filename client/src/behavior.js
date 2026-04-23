import { now } from "./helpers.js";

export const beh = {
  mouseMoves:       [],
  clicks:           [],
  keydowns:         [],
  touches:          [],
  scrolls:          [],
  copyPastes:       [],
  navigationEvents: [],
  _lastMouse:       0,
  _lastScroll:      0,
  _lastURL:         location.href,
};

document.addEventListener("mousemove", e => {
  const t = now();
  if (t - beh._lastMouse < 50) return;
  beh._lastMouse = t;
  if (beh.mouseMoves.length < 300)
    beh.mouseMoves.push([Math.round(e.clientX), Math.round(e.clientY), t]);
}, { passive: true });

document.addEventListener("click", e => {
  if (beh.clicks.length < 100)
    beh.clicks.push({ x: Math.round(e.clientX), y: Math.round(e.clientY), t: now(), button: e.button });
}, { passive: true });

document.addEventListener("keydown", e => {
  if (beh.keydowns.length < 200)
    beh.keydowns.push({ key: e.keyCode, t: now(), mod: (+e.ctrlKey) | (+e.shiftKey << 1) | (+e.altKey << 2) | (+e.metaKey << 3) });
}, { passive: true });

document.addEventListener("touchstart", e => {
  const t0 = e.touches[0];
  if (beh.touches.length < 100 && t0)
    beh.touches.push({ x: Math.round(t0.clientX), y: Math.round(t0.clientY), r: t0.radiusX || null, t: now() });
}, { passive: true });

window.addEventListener("scroll", () => {
  const t = now();
  if (t - beh._lastScroll < 100) return;
  beh._lastScroll = t;
  if (beh.scrolls.length < 100)
    beh.scrolls.push([Math.round(window.scrollX), Math.round(window.scrollY), t]);
}, { passive: true });

document.addEventListener("copy", e => {
  const text = (e.clipboardData || window.clipboardData).getData("text");
  if (beh.copyPastes.length < 50)
    beh.copyPastes.push({ type: "copy", content: text.slice(0, 100), t: now() });
}, { passive: true });

document.addEventListener("paste", e => {
  const text = (e.clipboardData || window.clipboardData).getData("text");
  if (beh.copyPastes.length < 50)
    beh.copyPastes.push({ type: "paste", content: text.slice(0, 100), t: now() });
}, { passive: true });

export function trackNavigation() {
  const currentURL = location.href;
  if (currentURL !== beh._lastURL) {
    if (beh.navigationEvents.length < 50)
      beh.navigationEvents.push({ from: beh._lastURL, to: currentURL, t: now() });
    beh._lastURL = currentURL;
  }
}

window.addEventListener("popstate", trackNavigation);
setInterval(trackNavigation, 1000);

import { safe } from "../helpers.js";

export function getOS() {
  const ua = navigator.userAgent;
  if (/Windows/i.test(ua)) return "Windows";
  if (/Mac OS X/i.test(ua)) return "macOS";
  if (/Linux/i.test(ua)) return "Linux";
  if (/iPhone|iPad/i.test(ua)) return "iOS";
  if (/Android/i.test(ua)) return "Android";
  return "Unknown";
}

export function collectNavigator() {
  const n = navigator;
  const ua = n.userAgent || "";
  const isWorkstation = !/Mobile|Android|iPhone|iPad|iPod|Windows Phone|BlackBerry|Opera Mini|IEMobile|WPDesktop/i.test(ua);
  return {
    userAgent:           ua,
    language:            n.language,
    platform:            n.platform,
    hardwareConcurrency: safe(() => n.hardwareConcurrency),
    deviceMemory:        safe(() => n.deviceMemory),
    vendor:              n.vendor,
    cookieEnabled:       n.cookieEnabled,
    onLine:              n.onLine,
    isWorkstation,
    isMobile:            !isWorkstation,
  };
}

export function collectOperatingSystem() {
  return getOS();
}

export function generateDeviceID(fingerprint) {
  const parts = [
    fingerprint.navigator.hardwareConcurrency || "0",
    fingerprint.navigator.deviceMemory || "0",
    fingerprint.screen.width,
    fingerprint.screen.height,
    fingerprint.screen.colorDepth,
    fingerprint.canvas?.dataURL?.slice(0, 50) || "nocanvas",
    fingerprint.timezone?.timezone || "unknown",
    fingerprint.operatingSystem || "unknown",
  ];

  const combined = parts.join("|");
  let hash = 0;
  for (let i = 0; i < combined.length; i++) {
    const char = combined.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return "dev_" + Math.abs(hash).toString(16).padStart(16, "0");
}

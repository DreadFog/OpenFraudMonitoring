/**
 * Device ID Extension — generates and persists a stable client-side UUID.
 *
 * This is the highest-confidence signal for device matching server-side
 * (see backend/services/device_matching.py): it survives fingerprint drift
 * (e.g. canvas randomization) as long as localStorage isn't cleared.
 *
 * Extension interface:
 *   name    – unique identifier
 *   collect – async, returns { uuid } sent as extensions.device_id
 */

const STORAGE_KEY = "ofm_device_id";

function generateUuid() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Fallback for environments without crypto.randomUUID
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function getOrCreateUuid() {
  try {
    let uuid = localStorage.getItem(STORAGE_KEY);
    if (!uuid) {
      uuid = generateUuid();
      localStorage.setItem(STORAGE_KEY, uuid);
    }
    return uuid;
  } catch (_) {
    // localStorage unavailable (e.g. private mode) — no persistent id this session
    return null;
  }
}

export default {
  name: "device_id",

  async collect() {
    return { uuid: getOrCreateUuid() };
  },
};

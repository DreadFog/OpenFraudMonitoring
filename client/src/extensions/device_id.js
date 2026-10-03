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

import { generateUuid } from "../uuid.js";

const STORAGE_KEY = "ofm_device_id";

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

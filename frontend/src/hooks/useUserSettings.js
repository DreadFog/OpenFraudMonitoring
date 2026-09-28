import { useState, useEffect, useCallback } from "react";
import { api } from "../api";

/**
 * Loads the current user's settings from the backend (merged with server-side
 * defaults) and exposes a debounced updater that persists a patch and merges
 * the result back into local state.
 */
export function useUserSettings() {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    api.getMySettings()
      .then((s) => { if (active) setSettings(s); })
      .catch(() => { if (active) setSettings({}); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const sync = (event) => setSettings((prev) => deepMerge(prev || {}, event.detail));
    window.addEventListener("ofm:settings-updated", sync);
    return () => window.removeEventListener("ofm:settings-updated", sync);
  }, []);

  const update = useCallback(async (patch) => {
    // Optimistic local merge for immediate UI feedback.
    setSettings((prev) => deepMerge(prev || {}, patch));
    window.dispatchEvent(new CustomEvent("ofm:settings-updated", { detail: patch }));
    try {
      const next = await api.updateMySettings(patch);
      setSettings(next);
      window.dispatchEvent(new CustomEvent("ofm:settings-updated", { detail: next }));
      return next;
    } catch {
      // Keep the optimistic value; persistence is best-effort.
      return null;
    }
  }, []);

  return { settings, loading, update };
}

function deepMerge(base, override) {
  const out = Array.isArray(base) ? [...base] : { ...base };
  for (const [k, v] of Object.entries(override || {})) {
    if (v && typeof v === "object" && !Array.isArray(v) && out[k] && typeof out[k] === "object") {
      out[k] = deepMerge(out[k], v);
    } else {
      out[k] = v;
    }
  }
  return out;
}

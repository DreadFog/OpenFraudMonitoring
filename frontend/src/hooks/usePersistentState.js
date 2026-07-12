import { useState, useEffect } from "react";
import { useAuth } from "../AuthContext";

/**
 * Drop-in replacement for useState that persists the value to localStorage,
 * namespaced per authenticated user so preferences don't leak across accounts
 * on a shared browser.
 *
 * @param {string} key          stable identifier for this piece of state
 * @param {*}      defaultValue value used when nothing has been stored yet
 * @returns {[any, Function]}   the same [value, setValue] tuple as useState
 */
export function usePersistentState(key, defaultValue) {
  const { user } = useAuth();
  const storageKey = `ofm_pref:${user?.id ?? "anon"}:${key}`;

  const [value, setValue] = useState(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      return stored !== null ? JSON.parse(stored) : defaultValue;
    } catch {
      return defaultValue;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(value));
    } catch {
      // Ignore quota / serialization errors — persistence is best-effort.
    }
  }, [storageKey, value]);

  return [value, setValue];
}

import { safe } from "../helpers.js";

export function collectStorage() {
  return {
    localStorage:   safe(() => { localStorage.setItem("_t", "1"); localStorage.removeItem("_t"); return true; }, false),
    sessionStorage: safe(() => { sessionStorage.setItem("_t", "1"); sessionStorage.removeItem("_t"); return true; }, false),
    indexedDB:      !!window.indexedDB,
    cookieEnabled:  navigator.cookieEnabled,
  };
}

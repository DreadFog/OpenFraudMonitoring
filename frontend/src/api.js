/**
 * API utilities for communicating with the backend
 * Uses relative URLs — proxied by Vite dev server or nginx in production
 */

export const api = {
  getSessions: async (filters = []) => {
    const params =
      filters.length > 0
        ? `?filters=${encodeURIComponent(JSON.stringify(filters))}`
        : "";
    const res = await fetch(`/api/sessions${params}`);
    if (!res.ok) throw new Error("Failed to fetch sessions");
    return res.json();
  },

  getSessionDetail: async (deviceId) => {
    const res = await fetch(`/api/sessions/${deviceId}`);
    if (!res.ok) throw new Error("Failed to fetch session detail");
    return res.json();
  },

  getStats: async () => {
    const res = await fetch("/api/stats");
    if (!res.ok) throw new Error("Failed to fetch stats");
    return res.json();
  },

  // ── Schema & suggestions (for filter builder) ──

  getSchema: async () => {
    const res = await fetch("/api/schema");
    if (!res.ok) throw new Error("Failed to fetch schema");
    return res.json();
  },

  getSuggestions: async (field, q) => {
    const res = await fetch(
      `/api/suggest?field=${encodeURIComponent(field)}&q=${encodeURIComponent(q)}`
    );
    if (!res.ok) throw new Error("Failed to fetch suggestions");
    return res.json();
  },

  // ── Rules CRUD ──

  getRules: async () => {
    const res = await fetch("/api/rules");
    if (!res.ok) throw new Error("Failed to fetch rules");
    return res.json();
  },

  createRule: async (rule) => {
    const res = await fetch("/api/rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rule),
    });
    if (!res.ok) throw new Error("Failed to create rule");
    return res.json();
  },

  updateRule: async (id, rule) => {
    const res = await fetch(`/api/rules/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rule),
    });
    if (!res.ok) throw new Error("Failed to update rule");
    return res.json();
  },

  deleteRule: async (id) => {
    const res = await fetch(`/api/rules/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete rule");
    return res.json();
  },
};

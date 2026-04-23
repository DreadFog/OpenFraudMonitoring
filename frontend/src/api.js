/**
 * API utilities for communicating with the backend
 * Uses relative URLs — proxied by Vite dev server or nginx in production
 */

export const api = {
  getSessions: async () => {
    const res = await fetch("/api/sessions");
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
};

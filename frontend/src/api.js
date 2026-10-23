/**
 * API utilities for communicating with the backend
 * Uses relative URLs — proxied by Vite dev server or nginx in production
 */

import { authFetch } from "./api/http";
import { graphApi } from "./api/graph";
import { intelligenceApi } from "./api/intelligence";
import { taxiiApi } from "./api/taxii";

export const api = {
  ...graphApi,
  ...intelligenceApi,
  ...taxiiApi,
  // ── Auth ──

  login: async (username, password) => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || "Login failed");
    }
    return res.json();
  },

  me: async () => {
    const res = await authFetch("/api/auth/me");
    if (!res.ok) throw new Error("Failed to fetch profile");
    return res.json();
  },

  changePassword: async (currentPassword, newPassword) => {
    const res = await authFetch("/api/auth/password", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || "Failed to change password");
    }
    return res.json();
  },

  // ── API Tokens ──

  getTokens: async () => {
    const res = await authFetch("/api/auth/tokens");
    if (!res.ok) throw new Error("Failed to fetch tokens");
    return res.json();
  },

  createToken: async (name, expiresAt = null) => {
    const res = await authFetch("/api/auth/tokens", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, expires_at: expiresAt }),
    });
    if (!res.ok) throw new Error("Failed to create token");
    return res.json();
  },

  revokeToken: async (tokenId) => {
    const res = await authFetch(`/api/auth/tokens/${tokenId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to revoke token");
    return res.json();
  },

  // ── Users (admin) ──

  getUsers: async () => {
    const res = await authFetch("/api/auth/users");
    if (!res.ok) throw new Error("Failed to fetch users");
    return res.json();
  },

  createUser: async (username, password, role) => {
    const res = await authFetch("/api/auth/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password: password || undefined, role }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || "Failed to create user");
    }
    return res.json();
  },

  updateUser: async (id, data) => {
    const res = await authFetch(`/api/auth/users/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to update user");
    return res.json();
  },

  deleteUser: async (id) => {
    const res = await authFetch(`/api/auth/users/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete user");
    return res.json();
  },

  // ── CORS Management (admin) ──

  getCorsOrigins: async () => {
    const res = await authFetch("/api/admin/cors/origins");
    if (!res.ok) throw new Error("Failed to fetch CORS origins");
    return res.json();
  },

  addCorsOrigin: async (origin) => {
    const res = await authFetch("/api/admin/cors/origins", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ origin }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || "Failed to add CORS origin");
    }
    return res.json();
  },

  deleteCorsOrigin: async (originId) => {
    const res = await authFetch(`/api/admin/cors/origins/${originId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete CORS origin");
    return res.json();
  },

  toggleCorsOrigin: async (originId) => {
    const res = await authFetch(`/api/admin/cors/origins/${originId}/toggle`, {
      method: "PATCH",
    });
    if (!res.ok) throw new Error("Failed to toggle CORS origin");
    return res.json();
  },

  // ── Monitored domains (admin) ──

  getDomainConfigs: async () => {
    const res = await authFetch("/api/admin/domains");
    if (!res.ok) throw new Error("Failed to fetch monitored domains");
    return res.json();
  },

  createDomainConfig: async (data) => {
    const res = await authFetch("/api/admin/domains", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || "Failed to create monitored domain");
    }
    return res.json();
  },

  updateDomainConfig: async (id, data) => {
    const res = await authFetch(`/api/admin/domains/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || "Failed to update monitored domain");
    }
    return res.json();
  },

  deleteDomainConfig: async (id) => {
    const res = await authFetch(`/api/admin/domains/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete monitored domain");
    return res.json();
  },

  exportDomainConfigs: async () => {
    const res = await authFetch("/api/admin/domains/export");
    if (!res.ok) throw new Error("Failed to export monitored domains");
    return res.json();
  },

  importDomainConfigs: async (data) => {
    const res = await authFetch("/api/admin/domains/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || "Failed to import monitored domains");
    }
    return res.json();
  },

  // ── Sessions ──

  getSessions: async (filters = [], sortBy = "last_seen", sortOrder = "desc", page = 1, perPage = 10) => {
    const params = new URLSearchParams();
    if (filters.length > 0) {
      params.append("filters", JSON.stringify(filters));
    }
    params.append("sort_by", sortBy);
    params.append("sort_order", sortOrder);
    params.append("page", String(page));
    params.append("per_page", String(perPage));
    
    const queryString = params.toString();
    const res = await authFetch(`/api/sessions${queryString ? '?' + queryString : ''}`);
    if (!res.ok) throw new Error("Failed to fetch sessions");
    return res.json();
  },

  getSessionDetail: async (sessionId) => {
    const res = await authFetch(`/api/sessions/${sessionId}`);
    if (!res.ok) throw new Error("Failed to fetch session detail");
    return res.json();
  },

  // ── Devices ──

  getDevices: async (page = 1, perPage = 10, filters = [], logic = "AND") => {
    const params = new URLSearchParams();
    params.append("page", String(page));
    params.append("per_page", String(perPage));
    if (filters.length > 0) {
      params.append("filters", JSON.stringify(filters));
      params.append("logic", logic);
    }
    const res = await authFetch(`/api/devices?${params.toString()}`);
    if (!res.ok) throw new Error("Failed to fetch devices");
    return res.json();
  },

  getDeviceSchema: async () => {
    const res = await authFetch("/api/devices/schema");
    if (!res.ok) throw new Error("Failed to fetch device schema");
    return res.json();
  },

  getDeviceSuggestions: async (field, q) => {
    const res = await authFetch(
      `/api/devices/suggest?field=${encodeURIComponent(field)}&q=${encodeURIComponent(q)}`
    );
    if (!res.ok) throw new Error("Failed to fetch device suggestions");
    return res.json();
  },

  getDeviceDetail: async (id, page = 1, perPage = 25) => {
    const res = await authFetch(`/api/devices/${id}?page=${page}&per_page=${perPage}`);
    if (!res.ok) throw new Error("Failed to fetch device detail");
    return res.json();
  },

  getStats: async () => {
    const res = await authFetch("/api/stats");
    if (!res.ok) throw new Error("Failed to fetch stats");
    return res.json();
  },

  getOverview: async () => {
    const res = await authFetch("/api/overview");
    if (!res.ok) throw new Error("Failed to fetch overview");
    return res.json();
  },

  overviewSearch: async (q) => {
    const res = await authFetch(`/api/overview/search?q=${encodeURIComponent(q)}`);
    if (!res.ok) throw new Error("Search failed");
    return res.json();
  },

  // ── Schema & suggestions (for filter builder) ──

  getSchema: async () => {
    const res = await authFetch("/api/schema");
    if (!res.ok) throw new Error("Failed to fetch schema");
    return res.json();
  },

  getSuggestions: async (field, q) => {
    const res = await authFetch(
      `/api/suggest?field=${encodeURIComponent(field)}&q=${encodeURIComponent(q)}`
    );
    if (!res.ok) throw new Error("Failed to fetch suggestions");
    return res.json();
  },

  // ── Rules CRUD ──

  getRules: async () => {
    const res = await authFetch("/api/rules");
    if (!res.ok) throw new Error("Failed to fetch rules");
    return res.json();
  },

  getSequenceSchema: async () => {
    const res = await authFetch("/api/rules/sequence-schema");
    if (!res.ok) throw new Error("Failed to fetch sequence schema");
    return res.json();
  },

  createRule: async (rule) => {
    const res = await authFetch("/api/rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rule),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || "Failed to create rule");
    return res.json();
  },

  updateRule: async (id, rule) => {
    const res = await authFetch(`/api/rules/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rule),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || "Failed to update rule");
    return res.json();
  },

  deleteRule: async (id) => {
    const res = await authFetch(`/api/rules/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete rule");
    return res.json();
  },

  deleteSession: async (sessionId) => {
    const res = await authFetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete session");
    return res.json();
  },

  // ── Dashboards CRUD ──

  getDashboards: async () => {
    const res = await authFetch("/api/dashboards");
    if (!res.ok) throw new Error("Failed to fetch dashboards");
    return res.json();
  },

  createDashboard: async (name, widgets) => {
    const res = await authFetch("/api/dashboards", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, widgets }),
    });
    if (!res.ok) throw new Error("Failed to create dashboard");
    return res.json();
  },

  updateDashboard: async (id, data) => {
    const res = await authFetch(`/api/dashboards/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to update dashboard");
    return res.json();
  },

  deleteDashboard: async (id) => {
    const res = await authFetch(`/api/dashboards/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete dashboard");
    return res.json();
  },

  // ── Widget data ──

  getWidgetData: async (widgetConfig) => {
    const res = await authFetch("/api/widget-data", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(widgetConfig),
    });
    if (!res.ok) throw new Error("Failed to fetch widget data");
    return res.json();
  },

  // ── Connectors / Logging ──

  getConnectorsStatus: async () => {
    const res = await authFetch("/api/connectors/status");
    if (!res.ok) throw new Error("Failed to fetch connector status");
    return res.json();
  },

  getConnectorsLogs: async (tail = 100) => {
    const res = await authFetch(`/api/connectors/logs?tail=${tail}`);
    if (!res.ok) throw new Error("Failed to fetch logs");
    return res.json();
  },

  // ── Settings ──

  getMySettings: async () => {
    const res = await authFetch("/api/settings/me");
    if (!res.ok) throw new Error("Failed to fetch settings");
    return res.json();
  },

  updateMySettings: async (patch) => {
    const res = await authFetch("/api/settings/me", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (!res.ok) throw new Error("Failed to update settings");
    return res.json();
  },

  getGlobalSettings: async () => {
    const res = await authFetch("/api/settings/global");
    if (!res.ok) throw new Error("Failed to fetch global settings");
    return res.json();
  },

  updateGlobalSettings: async (patch) => {
    const res = await authFetch("/api/settings/global", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || "Failed to update global settings");
    }
    return res.json();
  },

};

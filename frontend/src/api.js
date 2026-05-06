/**
 * API utilities for communicating with the backend
 * Uses relative URLs — proxied by Vite dev server or nginx in production
 */

function getToken() {
  return localStorage.getItem("ofm_token");
}

function authHeaders(extra = {}) {
  const token = getToken();
  const headers = { ...extra };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

async function authFetch(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: authHeaders(options.headers || {}),
  });
  if (res.status === 401) {
    localStorage.removeItem("ofm_token");
    localStorage.removeItem("ofm_user");
    window.location.href = "/login";
    throw new Error("Session expired");
  }
  return res;
}

export const api = {
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

  // ── Sessions ──

  getSessions: async (filters = []) => {
    const params =
      filters.length > 0
        ? `?filters=${encodeURIComponent(JSON.stringify(filters))}`
        : "";
    const res = await authFetch(`/api/sessions${params}`);
    if (!res.ok) throw new Error("Failed to fetch sessions");
    return res.json();
  },

  getSessionDetail: async (fsid) => {
    const res = await authFetch(`/api/sessions/${fsid}`);
    if (!res.ok) throw new Error("Failed to fetch session detail");
    return res.json();
  },

  getStats: async () => {
    const res = await authFetch("/api/stats");
    if (!res.ok) throw new Error("Failed to fetch stats");
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

  createRule: async (rule) => {
    const res = await authFetch("/api/rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rule),
    });
    if (!res.ok) throw new Error("Failed to create rule");
    return res.json();
  },

  updateRule: async (id, rule) => {
    const res = await authFetch(`/api/rules/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rule),
    });
    if (!res.ok) throw new Error("Failed to update rule");
    return res.json();
  },

  deleteRule: async (id) => {
    const res = await authFetch(`/api/rules/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete rule");
    return res.json();
  },

  deleteSession: async (fsid) => {
    const res = await authFetch(`/api/sessions/${encodeURIComponent(fsid)}`, { method: "DELETE" });
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

  // ── Intelligence ──

  getIpIntel: async (value) => {
    const res = await authFetch(`/api/intel/ip/${encodeURIComponent(value)}`);
    if (!res.ok) throw new Error("Failed to fetch IP intel");
    return res.json();
  },

  getEntityIntel: async (type, value) => {
    const res = await authFetch(`/api/intel/entity?type=${encodeURIComponent(type)}&value=${encodeURIComponent(value)}`);
    if (!res.ok) throw new Error("Failed to fetch entity intel");
    return res.json();
  },

  getIntelTypes: async () => {
    const res = await authFetch("/api/intel/types");
    if (!res.ok) throw new Error("Failed to fetch intel types");
    return res.json();
  },

  listEntities: async (type, limit = 25) => {
    const res = await authFetch(`/api/intel/entities?type=${encodeURIComponent(type)}&limit=${limit}`);
    if (!res.ok) throw new Error("Failed to fetch entities");
    return res.json();
  },

  triggerIntelLookup: async (connector, value) => {
    const res = await authFetch("/api/intel/lookup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ connector, value }),
    });
    if (!res.ok) throw new Error("Failed to trigger lookup");
    return res.json();
  },

  getEnrichers: async (entityType) => {
    const params = entityType ? `?entity_type=${encodeURIComponent(entityType)}` : "";
    const res = await authFetch(`/api/connectors/enrichers${params}`);
    if (!res.ok) throw new Error("Failed to fetch enrichers");
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
};

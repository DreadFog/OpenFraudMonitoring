import { authFetch } from "./http";

export const intelligenceApi = {
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

  createObservableIndicator: async (type, stixId) => {
    const res = await authFetch("/api/intel/indicators", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type, stix_id: stixId }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || "Failed to create indicator");
    }
    return res.json();
  },

  revokeIndicator: async (stixId) => {
    const res = await authFetch(`/api/intel/indicators/${encodeURIComponent(stixId)}/revoke`, { method: "POST" });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || "Failed to revoke indicator");
    }
    return res.json();
  },

  updateEntity: async (stixId, stixObject) => {
    const res = await authFetch(`/api/intel/entities/${encodeURIComponent(stixId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stix_object: stixObject }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || "Failed to update entity");
    }
    return res.json();
  },

  getEntitySessions: async (type, value, limit = 10) => {
    const res = await authFetch(`/api/intel/entity-sessions?type=${encodeURIComponent(type)}&value=${encodeURIComponent(value)}&limit=${limit}`);
    if (!res.ok) throw new Error("Failed to fetch entity sessions");
    return res.json();
  },

  getIntelTypes: async () => {
    const res = await authFetch("/api/intel/types");
    if (!res.ok) throw new Error("Failed to fetch intel types");
    return res.json();
  },

  getIntelFilterSchema: async (type) => {
    const params = type ? `?type=${encodeURIComponent(type)}` : "";
    const res = await authFetch(`/api/intel/filter-schema${params}`);
    if (!res.ok) throw new Error("Failed to fetch intel filter schema");
    return res.json();
  },

  listEntities: async (type, limit = 25, filters = [], logic = "AND") => {
    const params = new URLSearchParams();
    params.set("type", type);
    params.set("limit", String(limit));
    params.set("logic", logic || "AND");
    if (Array.isArray(filters) && filters.length > 0) {
      params.set("filters", JSON.stringify(filters));
    }
    const res = await authFetch(`/api/intel/entities?${params.toString()}`);
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
};

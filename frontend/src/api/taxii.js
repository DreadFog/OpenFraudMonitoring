import { authFetch } from "./http";

export const taxiiApi = {
  getExportFields: async (type) => {
    const res = await authFetch(`/api/taxii-feeds/export-fields?type=${encodeURIComponent(type)}`);
    if (!res.ok) throw new Error("Failed to fetch export fields");
    return res.json();
  },

  listTaxiiFeeds: async (includeInactive = false) => {
    const params = includeInactive ? "?include_inactive=true" : "";
    const res = await authFetch(`/api/taxii-feeds${params}`);
    if (!res.ok) throw new Error("Failed to fetch TAXII feeds");
    return res.json();
  },

  createTaxiiFeed: async (payload) => {
    const res = await authFetch("/api/taxii-feeds", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || "Failed to create TAXII feed");
    }
    return res.json();
  },

  updateTaxiiFeed: async (id, payload) => {
    const res = await authFetch(`/api/taxii-feeds/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || "Failed to update TAXII feed");
    }
    return res.json();
  },

  deleteTaxiiFeed: async (id) => {
    const res = await authFetch(`/api/taxii-feeds/${id}`, { method: "DELETE" });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || "Failed to delete TAXII feed");
    }
    return res.json();
  },
};

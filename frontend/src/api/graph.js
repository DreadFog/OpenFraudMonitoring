import { authFetch } from "./http";

export const graphApi = {
  graphSeed: async (seeds) => {
    const res = await authFetch("/api/graph/seed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seeds }),
    });
    if (!res.ok) throw new Error("Failed to build graph");
    return res.json();
  },

  graphExpansions: async (ref, knownIds = []) => {
    const res = await authFetch("/api/graph/expansions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ref, known_ids: knownIds }),
    });
    if (!res.ok) throw new Error("Failed to fetch expansions");
    return res.json();
  },

  graphExpand: async (ref, key) => {
    const res = await authFetch("/api/graph/expand", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ref, key }),
    });
    if (!res.ok) throw new Error("Failed to expand node");
    return res.json();
  },

  graphLinks: async (ref, knownIds = []) => {
    const res = await authFetch("/api/graph/links", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ref, known_ids: knownIds }),
    });
    if (!res.ok) throw new Error("Failed to compute links");
    return res.json();
  },
};

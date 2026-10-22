const FALLBACK = {
  session: "#3b82f6",
  property: "#a78bfa",
  flag: "#f59e0b",
  device: "#22d3ee",
  stix: {
    "ipv4-addr": "#10b981",
    "ipv6-addr": "#14b8a6",
    "user-agent": "#f59e0b",
    "autonomous-system": "#6366f1",
    location: "#ec4899",
    indicator: "#ef4444",
    malware: "#dc2626",
    campaign: "#8b5cf6",
    "intrusion-set": "#f97316",
  },
  ring: "#ef4444",
};

export const STIX_TYPES = [
  "ipv4-addr", "ipv6-addr", "user-agent", "autonomous-system",
  "location", "indicator", "malware", "campaign", "intrusion-set",
];

export const STIX_LABELS = {
  "ipv4-addr": "IPv4 Address",
  "ipv6-addr": "IPv6 Address",
  "user-agent": "User Agent",
  "autonomous-system": "Autonomous System",
  location: "Country",
  indicator: "Indicator",
  malware: "Malware",
  campaign: "Campaign",
  "intrusion-set": "Intrusion Set",
};

export function graphColors(settings) {
  const g = settings?.graph || {};
  const colors = g.colors || {};
  return {
    session: colors.session || FALLBACK.session,
    property: colors.property || FALLBACK.property,
    flag: colors.flag || FALLBACK.flag,
    device: colors.device || FALLBACK.device,
    stix: { ...FALLBACK.stix, ...(colors.stix || {}) },
    ring: g.riskRing?.color || FALLBACK.ring,
    ringEnabled: g.riskRing?.enabled !== false,
  };
}

function nodeColor(ele, colors) {
  const kind = ele.data("kind");
  if (kind === "session") return colors.session;
  if (kind === "property") return colors.property;
  if (kind === "flag") return colors.flag;
  if (kind === "device") return colors.device;
  if (kind === "stix") return colors.stix[ele.data("stixType")] || "#94a3b8";
  return "#94a3b8";
}

const clampRisk = (risk) => Math.max(0, Math.min(100, risk || 0));

export function buildStylesheet(colors) {
  const sessionStyle = {
    "background-color": colors.session,
    label: (ele) => (ele.data("risk") != null ? String(ele.data("risk")) : ""),
    "text-valign": "center",
    "text-halign": "center",
    color: "#ffffff",
    "font-weight": "bold",
    "font-size": "11px",
    "text-outline-width": 2,
    "text-outline-color": "#000000",
    "text-margin-y": 0,
    width: 34,
    height: 34,
  };
  if (colors.ringEnabled) {
    Object.assign(sessionStyle, {
      "pie-size": "100%",
      "pie-1-background-color": colors.ring,
      "pie-1-background-size": (ele) => clampRisk(ele.data("risk")),
      "pie-2-background-color": colors.session,
      "pie-2-background-size": (ele) => 100 - clampRisk(ele.data("risk")),
    });
  }
  return [
    {
      selector: "node",
      style: {
        "background-color": (ele) => nodeColor(ele, colors),
        label: "data(label)",
        color: "#e5e7eb",
        "font-size": "10px",
        "text-valign": "bottom",
        "text-halign": "center",
        "text-margin-y": 4,
        "text-outline-width": 2,
        "text-outline-color": "#0f172a",
        width: 26,
        height: 26,
        "border-width": 2,
        "border-color": "#0f172a",
      },
    },
    { selector: 'node[kind = "session"]', style: sessionStyle },
    { selector: 'node[kind = "property"]', style: { shape: "round-rectangle", width: 30, height: 22 } },
    { selector: 'node[kind = "device"]', style: { shape: "hexagon", "background-color": colors.device, width: 32, height: 32 } },
    { selector: 'node[kind = "stix"]', style: { shape: "diamond", width: 28, height: 28 } },
    {
      selector: 'node[kind = "flag"]',
      style: { shape: "triangle", "background-color": colors.flag, width: 30, height: 28 },
    },
    { selector: "node:selected", style: { "border-width": 3, "border-color": "#facc15" } },
    {
      selector: "edge",
      style: {
        width: 1.5,
        "line-color": "#475569",
        "target-arrow-color": "#475569",
        "curve-style": "bezier",
        label: "data(label)",
        "font-size": "8px",
        color: "#94a3b8",
        "text-rotation": "autorotate",
        "text-background-color": "#0f172a",
        "text-background-opacity": 0.7,
        "text-background-padding": 2,
      },
    },
    {
      selector: 'edge[kind = "stix_relationship"]',
      style: { "line-color": "#64748b", "target-arrow-shape": "triangle", "line-style": "solid" },
    },
    { selector: 'edge[kind = "metadata"]', style: { "line-style": "dashed" } },
  ];
}

export function mapNode(node) {
  return {
    group: "nodes",
    data: {
      id: node.id,
      label: node.kind === "flag" ? `⚠ ${node.label}` : node.kind === "device" ? `🖥 ${node.label}` : node.label,
      kind: node.kind,
      stixType: node.stix_type || null,
      risk: node.kind === "session" ? (node.data?.risk_score || 0) : null,
      ref: node.ref,
      meta: node.data || {},
    },
  };
}

export function mapEdge(edge) {
  return {
    group: "edges",
    data: { id: edge.id, source: edge.source, target: edge.target, label: edge.label, kind: edge.kind },
  };
}

import React, { useEffect, useLayoutEffect, useRef, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import cytoscape from "cytoscape";
import { api } from "../../api";
import { useUserSettings } from "../../hooks/useUserSettings";
import { parseSeeds } from "./graphLink";
import "./Graph.css";

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

const STIX_TYPES = [
  "ipv4-addr", "ipv6-addr", "user-agent", "autonomous-system",
  "location", "indicator", "malware", "campaign", "intrusion-set",
];

const STIX_LABELS = {
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

function graphColors(settings) {
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

const clampRisk = (r) => Math.max(0, Math.min(100, r || 0));

function buildStylesheet(colors) {
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

function mapNode(n) {
  return {
    group: "nodes",
    data: {
      id: n.id,
      label: n.kind === "flag" ? `⚠ ${n.label}` : n.kind === "device" ? `🖥 ${n.label}` : n.label,
      kind: n.kind,
      stixType: n.stix_type || null,
      risk: n.kind === "session" ? (n.data?.risk_score || 0) : null,
      ref: n.ref,
      meta: n.data || {},
    },
  };
}

function mapEdge(e) {
  return {
    group: "edges",
    data: { id: e.id, source: e.source, target: e.target, label: e.label, kind: e.kind },
  };
}

export default function Graph() {
  const [searchParams] = useSearchParams();
  const { settings, update } = useUserSettings();

  const containerRef = useRef(null);
  const cyRef = useRef(null);
  const colorsRef = useRef(graphColors(settings));
  const autoLinkRef = useRef(true);

  const [loading, setLoading] = useState(true);
  const [threshold, setThreshold] = useState(1000);
  const [menu, setMenu] = useState(null);
  const [expansions, setExpansions] = useState({ loading: false, items: [] });
  const [showSettings, setShowSettings] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [emptyNote, setEmptyNote] = useState("");
  const [nodeKinds, setNodeKinds] = useState({ session: false, property: false, flag: false, device: false, stix: [] });
  const [selInfo, setSelInfo] = useState({ count: 0, canBulk: false, kind: null });
  const [bulk, setBulk] = useState(null); // { loading, options, nodes }

  useEffect(() => {
    autoLinkRef.current = settings?.graph?.autoLink !== false;
  }, [settings]);

  const refreshNodeKinds = useCallback(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const stixSet = new Set();
    let session = false, property = false, flag = false, device = false;
    cy.nodes().forEach((n) => {
      const k = n.data("kind");
      if (k === "session") session = true;
      else if (k === "property") property = true;
      else if (k === "flag") flag = true;
      else if (k === "device") device = true;
      else if (k === "stix") stixSet.add(n.data("stixType"));
    });
    setNodeKinds({ session, property, flag, device, stix: Array.from(stixSet) });
  }, []);

  const updateSelInfo = useCallback(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const sel = cy.nodes(":selected");
    const count = sel.length;
    let canBulk = false;
    let kind = null;
    if (count >= 2) {
      kind = sel[0].data("kind");
      const stixType = sel[0].data("stixType");
      canBulk = sel.every((n) => n.data("kind") === kind && n.data("stixType") === stixType);
    }
    setSelInfo({ count, canBulk, kind });
  }, []);

  const mergeElements = useCallback((nodes, edges, sourcePos) => {
    const cy = cyRef.current;
    if (!cy) return 0;
    let added = 0;
    cy.batch(() => {
      for (const n of nodes || []) {
        if (cy.getElementById(n.id).nonempty()) continue;
        const el = cy.add(mapNode(n));
        if (sourcePos) {
          el.position({
            x: sourcePos.x + (Math.random() - 0.5) * 160,
            y: sourcePos.y + (Math.random() - 0.5) * 160,
          });
        }
        added += 1;
      }
      for (const e of edges || []) {
        if (cy.getElementById(e.id).nonempty()) continue;
        if (cy.getElementById(e.source).empty() || cy.getElementById(e.target).empty()) continue;
        cy.add(mapEdge(e));
      }
    });
    refreshNodeKinds();
    return added;
  }, [refreshNodeKinds]);

  const autoLinkNodes = useCallback(async (resNodes, beforeIds) => {
    if (!autoLinkRef.current) return;
    const cy = cyRef.current;
    if (!cy) return;
    const knownIds = cy.nodes().map((n) => n.id());
    for (const n of resNodes || []) {
      if (beforeIds.has(n.id)) continue;
      try {
        const links = await api.graphLinks(n.ref, knownIds);
        mergeElements([], links.edges);
      } catch { /* best-effort */ }
    }
  }, [mergeElements]);

  // ── Initialize Cytoscape once ──
  useEffect(() => {
    if (!containerRef.current || cyRef.current) return;
    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      style: buildStylesheet(colorsRef.current),
      minZoom: 0.05,
      maxZoom: 6,
      boxSelectionEnabled: true,
      selectionType: "single",
      wheelSensitivity: 1,
    });
    cyRef.current = cy;

    cy.on("cxttap", "node", (evt) => {
      const node = evt.target;
      const rendered = evt.renderedPosition || node.renderedPosition();
      openMenu(node, rendered);
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        setMenu(null);
        cy.elements().unselect();
      }
    });
    cy.on("pan zoom", () => setMenu(null));
    cy.on("select unselect", updateSelInfo);

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const down = (e) => {
      if ((e.key === "Control" || e.key === "Meta") && cyRef.current) cyRef.current.selectionType("additive");
    };
    const up = (e) => {
      if ((e.key === "Control" || e.key === "Meta") && cyRef.current) cyRef.current.selectionType("single");
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, []);

  // ── Load seeds on mount ──
  useEffect(() => {
    const seeds = parseSeeds(searchParams);
    if (seeds.length === 0) {
      setLoading(false);
      setEmptyNote("Graph is empty. Add an entity to start.");
      return;
    }
    setLoading(true);
    api.graphSeed(seeds)
      .then((res) => {
        setThreshold(res.threshold || 1000);
        mergeElements(res.nodes, res.edges);
        const cy = cyRef.current;
        if (cy && cy.nodes().length > 0) {
          cy.layout({ name: "cose", animate: false, padding: 40 }).run();
          cy.fit(undefined, 60);
        } else {
          setEmptyNote("No matching data found for the provided seeds.");
        }
      })
      .catch(() => setEmptyNote("Failed to load graph data."))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    colorsRef.current = graphColors(settings);
    if (cyRef.current) cyRef.current.style(buildStylesheet(colorsRef.current));
  }, [settings]);

  const openMenu = useCallback((node, renderedPos) => {
    const ref = node.data("ref");
    setMenu({
      x: renderedPos.x,
      y: renderedPos.y,
      ref,
      meta: node.data("meta") || {},
      kind: node.data("kind"),
      nodeId: node.id(),
    });
    setExpansions({ loading: true, items: [] });
    const knownIds = cyRef.current.nodes().map((n) => n.id());
    api.graphExpansions(ref, knownIds)
      .then((res) => setExpansions({ loading: false, items: res.expansions || [] }))
      .catch(() => setExpansions({ loading: false, items: [] }));
  }, []);

  const runExpansion = useCallback((opt) => {
    if (!menu) return;
    if (opt.warn || opt.count >= threshold) {
      const ok = window.confirm(
        `This expansion will add ${opt.count} nodes to the graph, which may impact performance. Continue?`
      );
      if (!ok) return;
    }
    const cy = cyRef.current;
    const sourceNode = cy.getElementById(menu.nodeId);
    const sourcePos = sourceNode.nonempty() ? { ...sourceNode.position() } : null;
    const beforeIds = new Set(cy.nodes().map((n) => n.id()));
    setMenu(null);
    api.graphExpand(menu.ref, opt.key)
      .then(async (res) => {
        mergeElements(res.nodes, res.edges, sourcePos);
        await autoLinkNodes(res.nodes, beforeIds);
      })
      .catch(() => {});
  }, [menu, threshold, mergeElements, autoLinkNodes]);

  const browseNode = useCallback((ref, meta, kind) => {
    if (kind === "session") {
      window.open(`/session/${meta.fsid}`, "_blank", "noopener");
    } else if (kind === "device") {
      window.open(`/device/${meta.id}`, "_blank", "noopener");
    } else if (kind === "stix") {
      window.open(
        `/intelligence?type=${encodeURIComponent(meta.stix_type)}&value=${encodeURIComponent(meta.value)}`,
        "_blank", "noopener"
      );
    }
    setMenu(null);
  }, []);

  const addEntity = useCallback(async (seed) => {
    try {
      const res = await api.graphSeed([seed]);
      if (!res.nodes || res.nodes.length === 0) {
        window.alert("No matching entity found.");
        return;
      }
      const cy = cyRef.current;
      const beforeIds = new Set(cy.nodes().map((n) => n.id()));
      const modelCenter = {
        x: (cy.width() / 2 - cy.pan().x) / cy.zoom(),
        y: (cy.height() / 2 - cy.pan().y) / cy.zoom(),
      };
      mergeElements(res.nodes, res.edges, modelCenter);
      setEmptyNote("");
      await autoLinkNodes(res.nodes, beforeIds);
      cy.fit(undefined, 60);
    } catch {
      window.alert("Failed to add entity.");
    }
  }, [mergeElements, autoLinkNodes]);

  // ── Bulk expansion ──
  const openBulk = useCallback(async () => {
    const cy = cyRef.current;
    if (!cy) return;
    const sel = cy.nodes(":selected");
    if (sel.length < 2) return;
    const kind = sel[0].data("kind");
    const stixType = sel[0].data("stixType");
    const same = sel.every((n) => n.data("kind") === kind && n.data("stixType") === stixType);
    if (!same) {
      window.alert("Bulk expand requires entities of the same type.");
      return;
    }
    const refs = sel.map((n) => n.data("ref"));
    setBulk({ loading: true, options: [], nodes: refs });
    const knownIds = cy.nodes().map((n) => n.id());
    const acc = new Map(); // key -> {key, category, group, count, refs:[]}
    for (const n of sel) {
      try {
        const res = await api.graphExpansions(n.data("ref"), knownIds);
        for (const o of res.expansions || []) {
          const e = acc.get(o.key) || { key: o.key, category: o.category || o.label, group: o.group, count: 0, refs: [] };
          e.count += o.count || 0;
          e.refs.push(n.data("ref"));
          acc.set(o.key, e);
        }
      } catch { /* ignore */ }
    }
    const options = Array.from(acc.values()).map((e) => ({
      ...e,
      label: e.category,
      warn: e.count >= threshold,
    }));
    setBulk({ loading: false, options, nodes: refs });
  }, [threshold]);

  const runBulk = useCallback(async (opt) => {
    if (opt.warn || opt.count >= threshold) {
      const ok = window.confirm(
        `This bulk expansion will add up to ${opt.count} nodes across ${opt.refs.length} entities. Continue?`
      );
      if (!ok) return;
    }
    setBulk(null);
    const cy = cyRef.current;
    for (const ref of opt.refs) {
      const beforeIds = new Set(cy.nodes().map((n) => n.id()));
      try {
        const res = await api.graphExpand(ref, opt.key);
        mergeElements(res.nodes, res.edges);
        await autoLinkNodes(res.nodes, beforeIds);
      } catch { /* ignore */ }
    }
    cy.fit(undefined, 60);
  }, [threshold, mergeElements, autoLinkNodes]);

  const relayout = () => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.layout({ name: "cose", animate: true, padding: 40 }).run();
    cy.fit(undefined, 60);
  };
  const fit = () => cyRef.current && cyRef.current.fit(undefined, 60);
  const zoomBy = (factor) => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  };

  const selectByType = (val) => {
    const cy = cyRef.current;
    if (!cy || !val) return;
    cy.elements().unselect();
    let sel = null;
    if (val === "session") sel = cy.nodes('[kind = "session"]');
    else if (val === "property") sel = cy.nodes('[kind = "property"]');
    else if (val === "flag") sel = cy.nodes('[kind = "flag"]');
    else if (val === "device") sel = cy.nodes('[kind = "device"]');
    else if (val.startsWith("stix:")) sel = cy.nodes(`[kind = "stix"][stixType = "${val.slice(5)}"]`);
    if (sel) sel.select();
  };

  const deleteSelected = () => {
    const cy = cyRef.current;
    if (!cy) return;
    const sel = cy.$(":selected");
    if (sel.empty()) return;
    sel.remove();
    setMenu(null);
    refreshNodeKinds();
    updateSelInfo();
  };

  return (
    <div className="graph-page">
      <div className="graph-canvas-wrap">
        <div ref={containerRef} className="graph-canvas" />

        {loading && <div className="graph-overlay">Loading graph…</div>}
        {!loading && emptyNote && <div className="graph-overlay">{emptyNote}</div>}

        {menu && (
          <GraphContextMenu
            menu={menu}
            expansions={expansions}
            threshold={threshold}
            onExpand={runExpansion}
            onBrowse={browseNode}
            onClose={() => setMenu(null)}
          />
        )}

        {showSettings && settings && (
          <GraphSettingsPanel settings={settings} onChange={update} onClose={() => setShowSettings(false)} />
        )}

        {showAdd && <AddEntityDrawer onAdd={addEntity} onClose={() => setShowAdd(false)} />}

        {bulk && (
          <BulkPanel bulk={bulk} threshold={threshold} onExpand={runBulk} onClose={() => setBulk(null)} />
        )}

        {/* Bottom control panel */}
        <div className="graph-bottom-panel">
          <div className="graph-bp-group">
            <button className="graph-btn" onClick={() => zoomBy(1.4)} title="Zoom in">＋</button>
            <button className="graph-btn" onClick={() => zoomBy(0.7)} title="Zoom out">－</button>
            <button className="graph-btn" onClick={fit} title="Fit to view">⤢ Fit</button>
            <button className="graph-btn" onClick={relayout} title="Re-run layout">↻ Layout</button>
            <button className="graph-btn" onClick={() => setShowSettings((v) => !v)}>⚙ Settings</button>
            <button className="graph-btn graph-btn-danger" onClick={deleteSelected} title="Delete selected nodes">🗑 Delete</button>
            <button
              className="graph-btn"
              onClick={openBulk}
              disabled={!selInfo.canBulk}
              title={selInfo.canBulk ? "Bulk expand selected entities" : "Select 2+ entities of the same type"}
            >
              ⛓ Bulk expand{selInfo.canBulk ? ` (${selInfo.count})` : ""}
            </button>
            <select
              className="graph-select"
              value=""
              onChange={(e) => selectByType(e.target.value)}
              title="Select nodes by type"
            >
              <option value="">Select by type…</option>
              {nodeKinds.session && <option value="session">Sessions</option>}
              {nodeKinds.property && <option value="property">Metadata</option>}
              {nodeKinds.flag && <option value="flag">Flags</option>}
              {nodeKinds.device && <option value="device">Devices</option>}
              {nodeKinds.stix.map((t) => (
                <option key={t} value={`stix:${t}`}>{STIX_LABELS[t] || t}</option>
              ))}
            </select>
          </div>
          <div className="graph-bp-spacer" />
          <button className="graph-add-btn" onClick={() => setShowAdd(true)}>＋ Add entity</button>
        </div>
      </div>
    </div>
  );
}

/* ── Reusable expansion option renderers ── */

function ExpButton({ opt, threshold, onExpand, labelText }) {
  const disabled = opt.count === 0;
  const warn = opt.warn || opt.count >= threshold;
  return (
    <button
      className={`graph-exp ${disabled ? "graph-exp-disabled" : ""}`}
      disabled={disabled}
      onClick={() => onExpand(opt)}
      title={disabled ? "Nothing new to add" : ""}
    >
      <span className="graph-exp-label">{labelText}</span>
      <span className={`graph-exp-count ${warn ? "graph-exp-warn" : ""}`}>
        {opt.count >= 1000 ? "1000+" : opt.count}
      </span>
    </button>
  );
}

function SearchableExpand({ title, options, threshold, onExpand }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const filtered = options.filter((o) =>
    (o.category || o.label || "").toLowerCase().includes(q.toLowerCase())
  );
  return (
    <div className="graph-exp-dd">
      <button className="graph-exp graph-exp-ddtoggle" onClick={() => setOpen((v) => !v)}>
        <span className="graph-exp-label">{title} ({options.length})</span>
        <span>{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="graph-exp-ddbody">
          <input
            className="graph-exp-search"
            placeholder={`Search ${title.toLowerCase()}…`}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            autoFocus
          />
          <div className="graph-exp-ddlist">
            {filtered.length === 0 && <div className="graph-menu-empty">No matches.</div>}
            {filtered.map((opt) => (
              <ExpButton
                key={opt.key}
                opt={opt}
                threshold={threshold}
                onExpand={onExpand}
                labelText={opt.category || opt.label}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ExpansionList({ options, threshold, onExpand }) {
  const groups = { linked: [], relationships: [], sessions: [], devices: [], property: [], flag: [] };
  for (const o of options) {
    (groups[o.group] || (groups[o.group] = [])).push(o);
  }
  return (
    <>
      {["linked", "relationships", "sessions", "devices"].flatMap((g) =>
        (groups[g] || []).map((opt) => (
          <ExpButton key={opt.key} opt={opt} threshold={threshold} onExpand={onExpand} labelText={opt.label} />
        ))
      )}
      {groups.property && groups.property.length > 0 && (
        <SearchableExpand title="Metadata" options={groups.property} threshold={threshold} onExpand={onExpand} />
      )}
      {groups.flag && groups.flag.length > 0 && (
        <SearchableExpand title="Flags" options={groups.flag} threshold={threshold} onExpand={onExpand} />
      )}
    </>
  );
}

function GraphContextMenu({ menu, expansions, threshold, onExpand, onBrowse, onClose }) {
  const panelRef = useRef(null);
  const [pos, setPos] = useState({ left: menu.x + 8, top: menu.y + 8, maxHeight: undefined });

  // Position the panel so it always fits inside the canvas: clamp horizontally,
  // cap the height to the available vertical space, and shift it up when it
  // would otherwise overflow the bottom edge.
  useLayoutEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const wrap = panel.offsetParent || panel.parentElement;
    if (!wrap) return;
    const wrapW = wrap.clientWidth;
    const wrapH = wrap.clientHeight;
    const margin = 12;
    const panelW = panel.offsetWidth || 300;

    // Measure natural height without any cap.
    const prev = panel.style.maxHeight;
    panel.style.maxHeight = "none";
    const natural = panel.offsetHeight;
    panel.style.maxHeight = prev;

    const maxHeight = Math.min(natural, wrapH - margin * 2);
    let left = Math.min(menu.x + 8, wrapW - panelW - margin);
    left = Math.max(margin, left);
    let top = menu.y + 8;
    if (top + maxHeight > wrapH - margin) top = wrapH - margin - maxHeight;
    if (top < margin) top = margin;

    setPos({ left, top, maxHeight });
  }, [menu, expansions]);

  const metaEntries = Object.entries(menu.meta || {}).filter(([, v]) => v !== null && v !== undefined && v !== "");
  const canBrowse = menu.kind === "session" || menu.kind === "stix" || menu.kind === "device";
  return (
    <div
      className="graph-menu"
      ref={panelRef}
      style={{ left: pos.left, top: pos.top, maxHeight: pos.maxHeight }}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="graph-menu-head">
        <span className="graph-menu-kind">{menu.kind}</span>
        <button className="graph-menu-close" onClick={onClose}>×</button>
      </div>

      <div className="graph-menu-section">
        <div className="graph-menu-label">Metadata</div>
        <div className="graph-menu-meta">
          {metaEntries.map(([k, v]) => (
            <div className="graph-menu-metarow" key={k}>
              <span className="graph-menu-metakey">{k}</span>
              <span className="graph-menu-metaval">{Array.isArray(v) ? v.join(", ") : String(v)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="graph-menu-section">
        <div className="graph-menu-label">Expand</div>
        {canBrowse && (
          <button className="graph-browse" onClick={() => onBrowse(menu.ref, menu.meta, menu.kind)}>
            🔎 Browse {menu.kind === "session" ? "session" : menu.kind === "device" ? "device" : "intelligence"} view
          </button>
        )}
        {expansions.loading && <div className="graph-menu-empty">Computing…</div>}
        {!expansions.loading && expansions.items.length === 0 && (
          <div className="graph-menu-empty">No expansions available.</div>
        )}
        {!expansions.loading && (
          <ExpansionList options={expansions.items} threshold={threshold} onExpand={onExpand} />
        )}
      </div>
    </div>
  );
}

function BulkPanel({ bulk, threshold, onExpand, onClose }) {
  return (
    <div className="graph-settings" onClick={(e) => e.stopPropagation()}>
      <div className="graph-settings-head">
        <span>Bulk expand · {bulk.nodes.length} entities</span>
        <button className="graph-menu-close" onClick={onClose}>×</button>
      </div>
      <div className="graph-settings-section">
        {bulk.loading && <div className="graph-menu-empty">Computing options…</div>}
        {!bulk.loading && bulk.options.length === 0 && (
          <div className="graph-menu-empty">No shared expansions for the selected entities.</div>
        )}
        {!bulk.loading && bulk.options.length > 0 && (
          <ExpansionList options={bulk.options} threshold={threshold} onExpand={onExpand} />
        )}
      </div>
    </div>
  );
}

const OP_LABELS = {
  eq: "=", neq: "≠", contains: "contains", not_contains: "not contains",
  starts_with: "starts with", ends_with: "ends with",
  gt: ">", gte: "≥", lt: "<", lte: "≤",
};

function normalizeSchema(fields) {
  return (fields || []).map((f) => ({
    name: f.name,
    label: f.label || f.name,
    type: f.type || "string",
    operators: (f.operators || []).map((op) => (typeof op === "string" ? { name: op } : op)),
  }));
}

function FieldCombo({ schema, value, onChange }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef(null);
  const selected = schema.find((f) => f.name === value);
  const filtered = schema.filter((f) => f.label.toLowerCase().includes(q.toLowerCase()));
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  return (
    <div className="graph-fc" ref={ref}>
      <button type="button" className="graph-fc-trigger" onClick={() => { setOpen((o) => !o); setQ(""); }}>
        {selected ? selected.label : "Field…"}
      </button>
      {open && (
        <div className="graph-fc-dd">
          <input
            className="graph-fc-search"
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search fields…"
          />
          <div className="graph-fc-list">
            {filtered.length === 0 && <div className="graph-menu-empty">No matches</div>}
            {filtered.slice(0, 200).map((f) => (
              <div key={f.name} className="graph-fc-item" onMouseDown={() => { onChange(f.name); setOpen(false); }}>
                {f.label}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function AddEntityDrawer({ onAdd, onClose }) {
  const [searchKind, setSearchKind] = useState("session"); // 'session' | <stix type>
  const [types, setTypes] = useState(STIX_TYPES);
  const [schema, setSchema] = useState([]);
  const [drafts, setDrafts] = useState([{ field: "", op: "", value: "" }]);
  const [applied, setApplied] = useState([]);
  const [logic, setLogic] = useState("AND");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [added, setAdded] = useState(() => new Set());

  const markAdded = (id) => setAdded((prev) => new Set(prev).add(id));

  // Available search kinds
  useEffect(() => {
    api.getIntelTypes()
      .then((r) => {
        const l = (r.types || []).map((t) => t.type);
        setTypes(l.length ? l : STIX_TYPES);
      })
      .catch(() => setTypes(STIX_TYPES));
  }, []);

  // Load the filter schema for the selected kind
  useEffect(() => {
    setDrafts([{ field: "", op: "", value: "" }]);
    setApplied([]);
    setLogic("AND");
    if (searchKind === "session") {
      api.getSchema().then((s) => setSchema(normalizeSchema(s))).catch(() => setSchema([]));
    } else if (searchKind === "device") {
      setSchema([]);
    } else {
      api.getIntelFilterSchema(searchKind).then((r) => setSchema(normalizeSchema(r.fields || []))).catch(() => setSchema([]));
    }
  }, [searchKind]);

  // Load results
  useEffect(() => {
    setLoading(true);
    setResults([]);
    const run = searchKind === "session"
      ? api.getSessions(applied, "last_seen", "desc", 1, 25).then((r) => r.sessions || [])
      : searchKind === "device"
      ? api.getDevices(1, 25).then((r) => r.devices || [])
      : api.listEntities(searchKind, 25, applied, logic).then((r) => r.entities || []);
    run.then(setResults).catch(() => setResults([])).finally(() => setLoading(false));
  }, [searchKind, applied, logic]);

  const updateDraft = (idx, patch) => setDrafts((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  const addDraft = () => setDrafts((prev) => [...prev, { field: "", op: "", value: "" }]);
  const removeDraft = (idx) => setDrafts((prev) => {
    const next = prev.filter((_, i) => i !== idx);
    return next.length ? next : [{ field: "", op: "", value: "" }];
  });

  const applyFilters = () => {
    const next = [];
    for (const row of drafts) {
      if (!row.field || !row.op) continue;
      const fd = schema.find((f) => f.name === row.field);
      if (!fd) continue;
      if (fd.type !== "boolean" && String(row.value || "").trim() === "") continue;
      next.push({
        field: row.field,
        op: row.op,
        value: fd.type === "boolean" ? String(row.value || "false") : String(row.value),
      });
    }
    setApplied(next);
  };

  const clearFilters = () => {
    setDrafts([{ field: "", op: "", value: "" }]);
    setApplied([]);
    setLogic("AND");
  };

  const addSession = (s) => {
    onAdd({ kind: "session", fsid: s.full_fsid });
    markAdded(`session:${s.full_fsid}`);
  };
  const addDevice = (d) => {
    onAdd({ kind: "device", id: d.id });
    markAdded(`device:${d.id}`);
  };
  const addEntity = (ent) => {
    onAdd({ kind: "stix", type: searchKind, value: ent.value });
    markAdded(`stix:${searchKind}:${ent.value}`);
  };

  const entityLabel = (ent) => {
    const name = ent.raw?.name;
    if (searchKind === "autonomous-system") return `AS${ent.value}${name ? ` · ${name}` : ""}`;
    return name || ent.value;
  };
  const relTime = (ms) => {
    if (!ms) return "";
    const s = Math.round((Date.now() - ms) / 1000);
    if (s < 60) return `${s}s`;
    if (s < 3600) return `${Math.round(s / 60)}m`;
    if (s < 86400) return `${Math.round(s / 3600)}h`;
    return `${Math.round(s / 86400)}d`;
  };

  const hasBoolField = (row) => {
    const fd = schema.find((f) => f.name === row.field);
    return fd && fd.type === "boolean";
  };

  return (
    <div className="graph-drawer" onClick={(e) => e.stopPropagation()}>
      <div className="graph-drawer-head">
        <span>Add entity</span>
        <button className="graph-menu-close" onClick={onClose}>×</button>
      </div>

      {/* What to search */}
      <div className="graph-drawer-section">
        <div className="graph-drawer-title">Search for</div>
        <select className="graph-select graph-drawer-select" value={searchKind} onChange={(e) => setSearchKind(e.target.value)}>
          <option value="session">Session</option>
          <option value="device">Device</option>
          {(types.length ? types : STIX_TYPES).map((t) => (
            <option key={t} value={t}>{STIX_LABELS[t] || t}</option>
          ))}
        </select>

        {/* Optional filters */}
        {searchKind !== "device" && (
        <>
        <div className="graph-drawer-title" style={{ marginTop: 10 }}>Filters (optional)</div>
        {searchKind !== "session" && (
          <select className="graph-select graph-drawer-select" value={logic} onChange={(e) => setLogic(e.target.value)}>
            <option value="AND">Match all (AND)</option>
            <option value="OR">Match any (OR)</option>
          </select>
        )}
        {drafts.map((row, idx) => {
          const fd = schema.find((f) => f.name === row.field);
          const ops = fd ? fd.operators : [];
          const isBool = hasBoolField(row);
          return (
            <div className="graph-filter-row" key={idx}>
              <FieldCombo schema={schema} value={row.field} onChange={(v) => updateDraft(idx, { field: v, op: "", value: "" })} />
              {!isBool && (
                <select className="graph-filter-op" value={row.op} onChange={(e) => updateDraft(idx, { op: e.target.value })} disabled={!row.field}>
                  <option value="">Op…</option>
                  {ops.map((op) => (
                    <option key={op.name} value={op.name}>{OP_LABELS[op.name] || op.label || op.name}</option>
                  ))}
                </select>
              )}
              {isBool ? (
                <select className="graph-filter-val" value={row.value || "true"} onChange={(e) => updateDraft(idx, { op: "eq", value: e.target.value })}>
                  <option value="true">True</option>
                  <option value="false">False</option>
                </select>
              ) : (
                <input className="graph-filter-val" type="text" value={row.value} onChange={(e) => updateDraft(idx, { value: e.target.value })} placeholder="Value…" />
              )}
              <button className="graph-filter-rm" onClick={() => removeDraft(idx)} title="Remove filter">×</button>
            </div>
          );
        })}
        <div className="graph-filter-actions">
          <button className="graph-btn" onClick={addDraft}>+ Filter</button>
          <button className="graph-btn" onClick={applyFilters}>Apply</button>
          <button className="graph-btn" onClick={clearFilters}>Clear</button>
        </div>
        </>
        )}
      </div>

      {/* Results */}
      <div className="graph-drawer-section">
        <div className="graph-drawer-title">Results{applied.length > 0 ? ` · ${applied.length} filter${applied.length > 1 ? "s" : ""}` : ""}</div>
        {loading && <div className="graph-menu-empty">Loading…</div>}
        {!loading && results.length === 0 && <div className="graph-menu-empty">No results.</div>}

        {!loading && searchKind === "session" && results.map((s) => {
          const id = `session:${s.full_fsid}`;
          const riskClass = s.risk_score >= 60 ? "risk-high" : s.risk_score >= 30 ? "risk-med" : "risk-low";
          return (
            <div className="graph-drawer-row" key={s.full_fsid}>
              <div className="graph-drawer-main">
                <div className="graph-drawer-idline">
                  <span className="graph-drawer-mono">{s.fsid}</span>
                  {(s.flags || []).slice(0, 3).map((f, i) => (
                    <span key={i} className="graph-drawer-flag">{String(f).split(":")[0]}</span>
                  ))}
                  {(s.flags || []).length > 3 && (
                    <span className="graph-drawer-flag">+{s.flags.length - 3}</span>
                  )}
                </div>
                <span className="graph-drawer-sub">{s.client_ip} · {relTime(s.last_seen)} ago</span>
              </div>
              <span className={`graph-drawer-risk ${riskClass}`}>{s.risk_score}</span>
              <button className="graph-drawer-add" disabled={added.has(id)} onClick={() => addSession(s)}>
                {added.has(id) ? "✓" : "+"}
              </button>
            </div>
          );
        })}

        {!loading && searchKind === "device" && results.map((d) => {
          const id = `device:${d.id}`;
          return (
            <div className="graph-drawer-row" key={d.id}>
              <div className="graph-drawer-main">
                <span className="graph-drawer-label">Device #{d.id} · {d.platform || "unknown"}</span>
                <span className="graph-drawer-sub">{d.webgl_renderer || "unknown GPU"} · {Math.round((d.confidence || 0) * 100)}% confidence</span>
              </div>
              <button className="graph-drawer-add" disabled={added.has(id)} onClick={() => addDevice(d)}>
                {added.has(id) ? "✓" : "+"}
              </button>
            </div>
          );
        })}

        {!loading && searchKind !== "session" && searchKind !== "device" && results.map((ent) => {
          const id = `stix:${searchKind}:${ent.value}`;
          return (
            <div className="graph-drawer-row" key={ent.stix_id || ent.value}>
              <div className="graph-drawer-main">
                <span className="graph-drawer-label">{entityLabel(ent)}</span>
                <span className="graph-drawer-sub">{ent.value}</span>
              </div>
              <button className="graph-drawer-add" disabled={added.has(id)} onClick={() => addEntity(ent)}>
                {added.has(id) ? "✓" : "+"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function GraphSettingsPanel({ settings, onChange, onClose }) {
  const colors = graphColors(settings);
  const g = settings.graph || {};

  const setSessionColor = (v) => onChange({ graph: { colors: { session: v } } });
  const setPropertyColor = (v) => onChange({ graph: { colors: { property: v } } });
  const setFlagColor = (v) => onChange({ graph: { colors: { flag: v } } });
  const setStixColor = (type, v) => onChange({ graph: { colors: { stix: { [type]: v } } } });
  const setRingEnabled = (v) => onChange({ graph: { riskRing: { enabled: v } } });
  const setRingColor = (v) => onChange({ graph: { riskRing: { color: v } } });
  const setAutoLink = (v) => onChange({ graph: { autoLink: v } });

  return (
    <div className="graph-settings" onClick={(e) => e.stopPropagation()}>
      <div className="graph-settings-head">
        <span>Graph Settings</span>
        <button className="graph-menu-close" onClick={onClose}>×</button>
      </div>

      <div className="graph-settings-section">
        <div className="graph-settings-label">Node colors</div>
        <ColorRow label="Session" value={colors.session} onChange={setSessionColor} />
        <ColorRow label="Metadata" value={colors.property} onChange={setPropertyColor} />
        <ColorRow label="Flag" value={colors.flag} onChange={setFlagColor} />
        {STIX_TYPES.map((t) => (
          <ColorRow key={t} label={STIX_LABELS[t] || t} value={colors.stix[t]} onChange={(v) => setStixColor(t, v)} />
        ))}
      </div>

      <div className="graph-settings-section">
        <div className="graph-settings-label">Session risk ring</div>
        <label className="graph-settings-toggle">
          <input type="checkbox" checked={g.riskRing?.enabled !== false} onChange={(e) => setRingEnabled(e.target.checked)} />
          Show risk ring
        </label>
        <ColorRow label="Ring color" value={colors.ring} onChange={setRingColor} />
      </div>

      <div className="graph-settings-section">
        <div className="graph-settings-label">Behavior</div>
        <label className="graph-settings-toggle">
          <input type="checkbox" checked={g.autoLink !== false} onChange={(e) => setAutoLink(e.target.checked)} />
          Automatically link new nodes to existing nodes
        </label>
      </div>
    </div>
  );
}

function ColorRow({ label, value, onChange }) {
  return (
    <div className="graph-color-row">
      <span className="graph-color-label">{label}</span>
      <input type="color" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

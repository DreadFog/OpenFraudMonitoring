import React, { useEffect, useRef, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import cytoscape from "cytoscape";
import { api } from "../../api";
import { useUserSettings } from "../../hooks/useUserSettings";
import { useRecentItems } from "../../hooks/useRecentItems";
import { buildGraphUrl, parseSeeds } from "./graphLink";
import { buildStylesheet, graphColors, mapEdge, mapNode, STIX_LABELS } from "./graphStyles";
import { AddEntityDrawer, BulkPanel, GraphContextMenu, GraphSettingsPanel } from "./GraphPanels";
import "./Graph.css";

export default function Graph() {
  const [searchParams] = useSearchParams();
  const [, recordRecent] = useRecentItems();
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
    recordRecent({
      key: `graph:${searchParams.get("seeds")}`,
      kind: "graph",
      label: `Graph · ${seeds.length} seed${seeds.length > 1 ? "s" : ""}`,
      sub: seeds.map((s) => s.kind === "session" ? `session #${s.id}` : s.kind === "device" ? `device #${s.id}` : `${s.type} ${s.value || ""}`).join(", "),
      path: buildGraphUrl(seeds),
    });
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
      window.open(`/session/${meta.id}`, "_blank", "noopener");
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

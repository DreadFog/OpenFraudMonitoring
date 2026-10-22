import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "../../api";
import { STIX_LABELS, STIX_TYPES } from "./graphStyles";

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

export function GraphContextMenu({ menu, expansions, threshold, onExpand, onBrowse, onClose }) {
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

export function BulkPanel({ bulk, threshold, onExpand, onClose }) {
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

export function AddEntityDrawer({ onAdd, onClose }) {
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
      api.getDeviceSchema().then((s) => setSchema(normalizeSchema(s))).catch(() => setSchema([]));
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
      ? api.getDevices(1, 25, applied, logic).then((r) => r.devices || [])
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
    onAdd({ kind: "session", id: s.id });
    markAdded(`session:${s.id}`);
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
    const name = ent.stix_object?.name;
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
      </div>

      {/* Results */}
      <div className="graph-drawer-section">
        <div className="graph-drawer-title">Results{applied.length > 0 ? ` · ${applied.length} filter${applied.length > 1 ? "s" : ""}` : ""}</div>
        {loading && <div className="graph-menu-empty">Loading…</div>}
        {!loading && results.length === 0 && <div className="graph-menu-empty">No results.</div>}

        {!loading && searchKind === "session" && results.map((s) => {
          const id = `session:${s.id}`;
          const riskClass = s.risk_score >= 60 ? "risk-high" : s.risk_score >= 30 ? "risk-med" : "risk-low";
          return (
            <div className="graph-drawer-row" key={s.id}>
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

export function GraphSettingsPanel({ settings, onChange, onClose }) {
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

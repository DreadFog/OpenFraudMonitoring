import React, { useState, useEffect } from "react";
import { api } from "../../api";
import "./Intelligence.css";

function parseIPv4(ip) {
  const parts = ip.split(".");
  if (parts.length !== 4) return null;
  const nums = [];
  for (const part of parts) {
    if (!/^\d{1,3}$/.test(part)) return null;
    const n = Number(part);
    if (n < 0 || n > 255) return null;
    nums.push(n);
  }
  return nums;
}

function expandIPv6(input) {
  const ip = input.toLowerCase();
  if (!ip.includes(":")) return null;
  if (ip.includes(".")) return null;
  const halves = ip.split("::");
  if (halves.length > 2) return null;

  const left = halves[0] ? halves[0].split(":").filter(Boolean) : [];
  const right = halves[1] ? halves[1].split(":").filter(Boolean) : [];

  for (const seg of [...left, ...right]) {
    if (!/^[0-9a-f]{1,4}$/.test(seg)) return null;
  }

  if (halves.length === 1) {
    if (left.length !== 8) return null;
    return left;
  }

  const missing = 8 - (left.length + right.length);
  if (missing <= 0) return null;
  return [...left, ...Array(missing).fill("0"), ...right];
}

function isPrivateIp(ip) {
  if (!ip) return false;
  const cleaned = String(ip).trim().replace(/^\[(.*)\]$/, "$1");

  const v4 = parseIPv4(cleaned);
  if (v4) {
    const [a, b] = v4;
    return a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
  }

  const v6 = expandIPv6(cleaned);
  if (v6) {
    const first = parseInt(v6[0], 16);
    return (first & 0xfe) === 0xfc;
  }

  return false;
}

function isIpEntityType(type) {
  return type === "ipv4-addr" || type === "ipv6-addr";
}

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
  } catch {
    return String(iso);
  }
}

function ObjectLabel({ obj, onClick }) {
  if (!obj) return <span className="intel-muted">—</span>;
  const { stix_type, value, raw } = obj;
  const r = raw || {};
  const wrap = (content) => onClick
    ? <span className="intel-link" onClick={(e) => { e.stopPropagation(); onClick(stix_type, value); }}>{content}</span>
    : <span>{content}</span>;
  if (stix_type === "indicator") return wrap(<><b>indicator</b> · {r.name || r.pattern || value}</>);
  if (stix_type === "malware") return wrap(<><b>malware</b> · {r.name || value}</>);
  if (stix_type === "campaign") return wrap(<><b>campaign</b> · {r.name || value}</>);
  if (stix_type === "intrusion-set") return wrap(<><b>intrusion-set</b> · {r.name || value}</>);
  if (stix_type === "autonomous-system") return wrap(<><b>AS</b> · {r.number ? `AS${r.number}` : value} {r.name ? `(${r.name})` : ""}</>);
  if (stix_type === "location") return wrap(<><b>country</b> · {r.name || value}</>);
  return wrap(<><b>{stix_type}</b> · {value}</>);
}

const TYPE_LABELS = {
  "ipv4-addr": "IPv4 Address",
  "ipv6-addr": "IPv6 Address",
  "user-agent": "User Agent",
  "autonomous-system": "Autonomous System",
  "location": "Country",
  "indicator": "Indicator",
  "malware": "Malware",
  "campaign": "Campaign",
  "intrusion-set": "Intrusion Set",
};

const TYPE_PLACEHOLDERS = {
  "ipv4-addr": "Enter an IPv4 address…",
  "ipv6-addr": "Enter an IPv6 address…",
  "user-agent": "Enter a user-agent string…",
  "autonomous-system": "Enter an AS number…",
  "location": "Enter a country code (e.g. US)…",
  "indicator": "Enter an indicator pattern…",
  "malware": "Enter a malware name…",
  "campaign": "Enter a campaign name…",
  "intrusion-set": "Enter an intrusion-set name…",
};

export default function Intelligence() {
  const [entityType, setEntityType] = useState("");
  const [availableTypes, setAvailableTypes] = useState([]);
  const [query, setQuery] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showRaw, setShowRaw] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNote, setRefreshNote] = useState("");
  const [enrichers, setEnrichers] = useState([]);
  const [enrichOpen, setEnrichOpen] = useState(false);
  const [entities, setEntities] = useState([]);
  const [entitiesLoading, setEntitiesLoading] = useState(false);
  const [limit, setLimit] = useState(25);
  const [filterSchema, setFilterSchema] = useState([]);
  const [filters, setFilters] = useState([]);
  const [filterLogic, setFilterLogic] = useState("AND");
  const [filterDrafts, setFilterDrafts] = useState([{ field: "", op: "", value: "" }]);

  // Fetch available entity types on mount
  useEffect(() => {
    api.getIntelTypes()
      .then((r) => {
        setAvailableTypes(r.types || []);
        if (r.types?.length > 0 && !entityType) {
          setEntityType(r.types[0].type);
        }
      })
      .catch(() => setAvailableTypes([]));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch filter schema when entity type changes
  useEffect(() => {
    if (!entityType) {
      setFilterSchema([]);
      return;
    }

    api.getIntelFilterSchema(entityType)
      .then((r) => {
        setFilterSchema(r.fields || []);
        setFilterDrafts([{ field: "", op: "", value: "" }]);
        setFilters([]);
      })
      .catch(() => {
        setFilterSchema([]);
        setFilterDrafts([{ field: "", op: "", value: "" }]);
        setFilters([]);
      });
  }, [entityType]);

  // Auto-load latest entities when type/limit/filters change
  useEffect(() => {
    if (!entityType) return;
    setEntitiesLoading(true);
    setEntities([]);
    api.listEntities(entityType, limit, filters, filterLogic)
      .then((r) => setEntities(r.entities || []))
      .catch(() => setEntities([]))
      .finally(() => setEntitiesLoading(false));
  }, [entityType, limit, filters, filterLogic]);

  const schemaFieldByName = (name) => filterSchema.find((f) => f.name === name);

  const addFilterDraft = () => {
    setFilterDrafts((prev) => [...prev, { field: "", op: "", value: "" }]);
  };

  const removeFilterDraft = (idx) => {
    setFilterDrafts((prev) => {
      const next = prev.filter((_, i) => i !== idx);
      return next.length ? next : [{ field: "", op: "", value: "" }];
    });
  };

  const updateFilterDraft = (idx, patch) => {
    setFilterDrafts((prev) => prev.map((row, i) => (i === idx ? { ...row, ...patch } : row)));
  };

  const applyFilters = () => {
    const next = [];
    for (const row of filterDrafts) {
      if (!row.field || !row.op) continue;
      const meta = schemaFieldByName(row.field);
      if (!meta) continue;
      const rawValue = row.value;
      if (meta.type !== "boolean" && String(rawValue || "").trim() === "") continue;
      next.push({
        field: row.field,
        op: row.op,
        value: meta.type === "boolean" ? String(rawValue || "false") : String(rawValue),
      });
    }
    setFilters(next);
  };

  const clearFilters = () => {
    setFilterDrafts([{ field: "", op: "", value: "" }]);
    setFilters([]);
    setFilterLogic("AND");
  };

  const runSearch = async (e) => {
    if (e) e.preventDefault();
    const v = query.trim();
    if (!v || !entityType) return;
    setLoading(true);
    setError("");
    setData(null);
    setShowRaw(false);
    setEnrichers([]);
    setEnrichOpen(false);
    if (isIpEntityType(entityType) && isPrivateIp(v)) {
      setData({
        privateIp: true,
        value: v,
        type: entityType,
      });
      setLoading(false);
      return;
    }
    try {
      const result = await api.getEntityIntel(entityType, v);
      setData(result);
      if (result.found && result.observable) {
        try {
          const er = await api.getEnrichers(result.observable.stix_type);
          setEnrichers(er.enrichers || []);
        } catch {
          setEnrichers([]);
        }
      }
    } catch (err) {
      setError(err.message || "Lookup failed");
    } finally {
      setLoading(false);
    }
  };

  const selectEntity = async (type, value) => {
    // Allow navigating to any entity type
    if (type && type !== entityType) {
      setEntityType(type);
    }
    setQuery(value);
    setLoading(true);
    setError("");
    setData(null);
    setShowRaw(false);
    setEnrichers([]);
    setEnrichOpen(false);
    const nextType = type || entityType;
    if (isIpEntityType(nextType) && isPrivateIp(value)) {
      setData({
        privateIp: true,
        value,
        type: nextType,
      });
      setLoading(false);
      return;
    }
    try {
      const result = await api.getEntityIntel(nextType, value);
      setData(result);
      if (result.found && result.observable) {
        try {
          const er = await api.getEnrichers(result.observable.stix_type);
          setEnrichers(er.enrichers || []);
        } catch {
          setEnrichers([]);
        }
      }
    } catch (err) {
      setError(err.message || "Lookup failed");
    } finally {
      setLoading(false);
    }
  };

  const triggerEnrich = async (connectorName) => {
    if (!query.trim()) return;
    setRefreshing(true);
    setRefreshNote("");
    setEnrichOpen(false);
    try {
      const r = await api.triggerIntelLookup(connectorName, query.trim());
      setRefreshNote(`Enrichment via ${connectorName} queued (${r.request_id.slice(0, 8)}…). Re-search in a few seconds.`);
    } catch (err) {
      setRefreshNote(err.message || "Enrichment failed");
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="intel-page">
      <header className="intel-header">
        <h1>Intelligence</h1>
        <p className="intel-sub">Browse cached threat intelligence by entity type and value.</p>
      </header>

      <form className="intel-search" onSubmit={runSearch}>
        <select
          className="intel-select"
          value={entityType}
          onChange={(e) => { setEntityType(e.target.value); setData(null); setEnrichers([]); setQuery(""); }}
        >
          {availableTypes.length === 0 && <option value="">No entities in database</option>}
          {availableTypes.map((t) => (
            <option key={t.type} value={t.type}>
              {TYPE_LABELS[t.type] || t.type} ({t.count})
            </option>
          ))}
        </select>
        <input
          className="intel-input"
          type="text"
          placeholder={TYPE_PLACEHOLDERS[entityType] || "Enter a value…"}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button className="intel-btn intel-btn-primary" type="submit" disabled={loading}>
          {loading ? "Searching…" : "Search"}
        </button>
        <div className="intel-enrich-wrap">
          <button
            className="intel-btn"
            type="button"
            onClick={() => setEnrichOpen((v) => !v)}
            disabled={refreshing || !query.trim() || enrichers.length === 0}
            title={enrichers.length === 0 ? "No enrichers available for this entity type" : "Enrich via a connector"}
          >
            {refreshing ? "Enriching…" : "⚡ Enrich"}{enrichers.length > 0 ? ` (${enrichers.length})` : ""}
          </button>
          {enrichOpen && enrichers.length > 0 && (
            <div className="intel-enrich-dropdown">
              {enrichers.map((c) => (
                <button
                  key={c.name}
                  className="intel-enrich-option"
                  type="button"
                  onClick={() => triggerEnrich(c.name)}
                >
                  <span className="intel-enrich-name">{c.name}</span>
                  <span className="intel-enrich-scope">{c.scope.join(", ")}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </form>

      {!data && entityType && (
        <section className="intel-card intel-filters-card">
          <div className="intel-card-head">
            <h2>Filters</h2>
            <span className="intel-count">{filters.length} active</span>
            <select
              className="intel-limit-select"
              value={filterLogic}
              onChange={(e) => setFilterLogic(e.target.value)}
            >
              <option value="AND">Match all (AND)</option>
              <option value="OR">Match any (OR)</option>
            </select>
          </div>

          {filterDrafts.map((row, idx) => {
            const meta = schemaFieldByName(row.field);
            const operators = meta?.operators || [];
            const isBoolean = meta?.type === "boolean";
            return (
              <div key={idx} className="intel-filter-row">
                <select
                  className="intel-select"
                  value={row.field}
                  onChange={(e) => updateFilterDraft(idx, { field: e.target.value, op: "", value: "" })}
                >
                  <option value="">Field…</option>
                  {filterSchema.map((f) => (
                    <option key={f.name} value={f.name}>{f.label}</option>
                  ))}
                </select>

                <select
                  className="intel-select"
                  value={row.op}
                  onChange={(e) => updateFilterDraft(idx, { op: e.target.value })}
                  disabled={!row.field}
                >
                  <option value="">Operator…</option>
                  {operators.map((op) => (
                    <option key={op} value={op}>{op}</option>
                  ))}
                </select>

                {isBoolean ? (
                  <select
                    className="intel-select"
                    value={row.value || "false"}
                    onChange={(e) => updateFilterDraft(idx, { value: e.target.value })}
                    disabled={!row.op}
                  >
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                ) : (
                  <input
                    className="intel-input"
                    type="text"
                    value={row.value}
                    onChange={(e) => updateFilterDraft(idx, { value: e.target.value })}
                    placeholder={meta ? `Value (${meta.type})` : "Value…"}
                    disabled={!row.op}
                  />
                )}

                <button
                  className="intel-btn"
                  type="button"
                  onClick={() => removeFilterDraft(idx)}
                >
                  Remove
                </button>
              </div>
            );
          })}

          <div className="intel-filter-actions">
            <button className="intel-btn" type="button" onClick={addFilterDraft}>+ Add filter</button>
            <button className="intel-btn intel-btn-primary" type="button" onClick={applyFilters}>Apply filters</button>
            <button className="intel-btn" type="button" onClick={clearFilters}>Clear</button>
          </div>
        </section>
      )}

      {refreshNote && <div className="intel-note">{refreshNote}</div>}
      {error && <div className="intel-error">{error}</div>}

      {/* Entity listing */}
      {!data && (
        <section className="intel-card">
          <div className="intel-card-head">
            <h2>{TYPE_LABELS[entityType] || entityType} entities</h2>
            <span className="intel-count">
              {entitiesLoading ? "loading…" : `${entities.length} shown`}
            </span>
            <select
              className="intel-limit-select"
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            >
              <option value={25}>Latest 25</option>
              <option value={50}>Latest 50</option>
              <option value={100}>Latest 100</option>
            </select>
          </div>
          {entities.length === 0 && !entitiesLoading && (
            <p className="intel-muted">No entities of this type in the database.</p>
          )}
          {entities.length > 0 && (
            <div className="intel-table-wrap">
              <table className="intel-table intel-entity-list">
                <thead>
                  <tr>
                    <th>Value</th>
                    <th>Created</th>
                    <th>Last Refreshed</th>
                    <th>Decay</th>
                  </tr>
                </thead>
                <tbody>
                  {entities.map((ent) => (
                    <tr
                      key={ent.stix_id}
                      className="intel-entity-row"
                      onClick={() => selectEntity(entityType, ent.value)}
                    >
                      <td className="intel-entity-value">{ent.value}</td>
                      <td>{fmtDate(ent.created_at_platform)}</td>
                      <td>{fmtDate(ent.last_refreshed_at)}</td>
                      <td>{ent.decayed
                        ? <span className="intel-pill intel-pill-decayed">decayed</span>
                        : <span className="intel-muted">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {data?.privateIp && (
        <div className="intel-empty">
          <b>{data.value}</b> is a private IP address. Intelligence lookup is skipped for private ranges.
        </div>
      )}

      {data && !data.privateIp && !data.found && (
        <div className="intel-empty">
          No cached intelligence for <code>{data.value}</code> ({data.type || entityType}).
          Use <em>Enrich</em> to query a connector.
        </div>
      )}

      {data && !data.privateIp && data.found && (
        <div className="intel-results">
          <button
            className="intel-btn intel-back-btn"
            type="button"
            onClick={() => { setData(null); setShowRaw(false); setEnrichers([]); setEnrichOpen(false); }}
          >
            ← Back to list
          </button>
          <section className="intel-card">
            <div className="intel-card-head">
              <h2>{data.observable.value}</h2>
              <div className="intel-pill">{data.observable.stix_type}</div>
              {data.observable.decayed && <div className="intel-pill intel-pill-decayed">decayed</div>}
            </div>
            <div className="intel-meta">
              <div><span>Created on platform</span><b>{fmtDate(data.observable.created_at_platform)}</b></div>
              <div><span>Last refreshed</span><b>{fmtDate(data.observable.last_refreshed_at)}</b></div>
              <div><span>STIX ID</span><code>{data.observable.stix_id}</code></div>
              {data.session_count != null && (
                <div><span>Sessions</span><b>{data.session_count}</b></div>
              )}
            </div>
          </section>

          {(data.autonomous_system || data.country) && (
            <section className="intel-grid">
              {data.autonomous_system && (
                <div className="intel-mini">
                  <div className="intel-mini-label">Autonomous System</div>
                  <div className="intel-mini-value">
                    <ObjectLabel obj={data.autonomous_system} onClick={selectEntity} />
                  </div>
                </div>
              )}
              {data.country && (
                <div className="intel-mini">
                  <div className="intel-mini-label">Country</div>
                  <div className="intel-mini-value">
                    <ObjectLabel obj={data.country} onClick={selectEntity} />
                  </div>
                </div>
              )}
            </section>
          )}

          <section className="intel-card">
            <div className="intel-card-head">
              <h2>Relationships</h2>
              <span className="intel-count">{data.relationships.length}</span>
            </div>
            {data.relationships.length === 0 ? (
              <p className="intel-muted">No relationships cached.</p>
            ) : (
              <div className="intel-table-wrap">
                <table className="intel-table">
                  <thead>
                    <tr>
                      <th>Source</th>
                      <th>Type</th>
                      <th>Target</th>
                      <th>Decay</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.relationships.map((r) => (
                      <tr key={r.stix_id} className="intel-rel-row">
                        <td><ObjectLabel obj={r.source} onClick={selectEntity} /></td>
                        <td><span className="intel-rel-type">{r.relationship_type}</span></td>
                        <td><ObjectLabel obj={r.target} onClick={selectEntity} /></td>
                        <td>{r.decayed
                          ? <span className="intel-pill intel-pill-decayed">decayed</span>
                          : <span className="intel-muted">—</span>}</td>
                        <td className="intel-rel-dates">
                          <div>Created: {fmtDate(r.created_at_platform)}</div>
                          <div>Start: {fmtDate(r.start_time)}</div>
                          <div>Stop: {fmtDate(r.stop_time)}</div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="intel-card">
            <button className="intel-btn" type="button" onClick={() => setShowRaw((v) => !v)}>
              {showRaw ? "Hide raw data" : "Show raw data"}
            </button>
            {showRaw && (
              <pre className="intel-raw">{JSON.stringify(data, null, 2)}</pre>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

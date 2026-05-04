import React, { useState, useEffect } from "react";
import { api } from "../../api";
import "./Intelligence.css";

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

  // Auto-load latest entities when type or limit changes
  useEffect(() => {
    if (!entityType) return;
    setEntitiesLoading(true);
    setEntities([]);
    api.listEntities(entityType, limit)
      .then((r) => setEntities(r.entities || []))
      .catch(() => setEntities([]))
      .finally(() => setEntitiesLoading(false));
  }, [entityType, limit]);

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
    try {
      const result = await api.getEntityIntel(type || entityType, value);
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

      {data && !data.found && (
        <div className="intel-empty">
          No cached intelligence for <code>{data.value}</code> ({data.type || entityType}).
          Use <em>Enrich</em> to query a connector.
        </div>
      )}

      {data && data.found && (
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

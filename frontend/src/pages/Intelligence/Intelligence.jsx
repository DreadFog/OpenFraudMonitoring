import React, { useState } from "react";
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

function ObjectLabel({ obj }) {
  if (!obj) return <span className="intel-muted">—</span>;
  const { stix_type, value, raw } = obj;
  const r = raw || {};
  if (stix_type === "indicator") return <span><b>indicator</b> · {r.name || r.pattern || value}</span>;
  if (stix_type === "malware") return <span><b>malware</b> · {r.name || value}</span>;
  if (stix_type === "campaign") return <span><b>campaign</b> · {r.name || value}</span>;
  if (stix_type === "intrusion-set") return <span><b>intrusion-set</b> · {r.name || value}</span>;
  if (stix_type === "autonomous-system") return <span><b>AS</b> · {r.number ? `AS${r.number}` : value} {r.name ? `(${r.name})` : ""}</span>;
  if (stix_type === "location") return <span><b>country</b> · {r.name || value}</span>;
  return <span><b>{stix_type}</b> · {value}</span>;
}

export default function Intelligence() {
  const [query, setQuery] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showRaw, setShowRaw] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNote, setRefreshNote] = useState("");

  const runSearch = async (e) => {
    if (e) e.preventDefault();
    const v = query.trim();
    if (!v) return;
    setLoading(true);
    setError("");
    setData(null);
    setShowRaw(false);
    try {
      const result = await api.getIpIntel(v);
      setData(result);
    } catch (err) {
      setError(err.message || "Lookup failed");
    } finally {
      setLoading(false);
    }
  };

  const forceRefresh = async () => {
    if (!query.trim()) return;
    setRefreshing(true);
    setRefreshNote("");
    try {
      const r = await api.triggerIntelLookup("opencti", query.trim());
      setRefreshNote(`Lookup queued (request ${r.request_id.slice(0, 8)}…). Re-search in a few seconds.`);
    } catch (err) {
      setRefreshNote(err.message || "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="intel-page">
      <header className="intel-header">
        <h1>Intelligence</h1>
        <p className="intel-sub">Browse cached threat intelligence by IP address.</p>
      </header>

      <form className="intel-search" onSubmit={runSearch}>
        <input
          className="intel-input"
          type="text"
          placeholder="Enter an IPv4 or IPv6 address…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button className="intel-btn intel-btn-primary" type="submit" disabled={loading}>
          {loading ? "Searching…" : "Search"}
        </button>
        <button
          className="intel-btn"
          type="button"
          onClick={forceRefresh}
          disabled={refreshing || !query.trim()}
          title="Trigger a fresh OpenCTI query"
        >
          {refreshing ? "Queuing…" : "↻ Force refresh"}
        </button>
      </form>

      {refreshNote && <div className="intel-note">{refreshNote}</div>}
      {error && <div className="intel-error">{error}</div>}

      {data && !data.found && (
        <div className="intel-empty">
          No cached intelligence for <code>{data.value}</code>.
          Click <em>Force refresh</em> to query the connector.
        </div>
      )}

      {data && data.found && (
        <div className="intel-results">
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
            </div>
          </section>

          <section className="intel-grid">
            <div className="intel-mini">
              <div className="intel-mini-label">Autonomous System</div>
              <div className="intel-mini-value">
                {data.autonomous_system
                  ? <ObjectLabel obj={data.autonomous_system} />
                  : <span className="intel-muted">NA</span>}
              </div>
            </div>
            <div className="intel-mini">
              <div className="intel-mini-label">Country</div>
              <div className="intel-mini-value">
                {data.country
                  ? <ObjectLabel obj={data.country} />
                  : <span className="intel-muted">NA</span>}
              </div>
            </div>
          </section>

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
                      <th>Created</th>
                      <th>Start</th>
                      <th>Stop</th>
                      <th>Decay</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.relationships.map((r) => (
                      <tr key={r.stix_id}>
                        <td><ObjectLabel obj={r.source} /></td>
                        <td><span className="intel-rel-type">{r.relationship_type}</span></td>
                        <td><ObjectLabel obj={r.target} /></td>
                        <td>{fmtDate(r.created_at_platform)}</td>
                        <td>{fmtDate(r.start_time)}</td>
                        <td>{fmtDate(r.stop_time)}</td>
                        <td>{r.decayed
                          ? <span className="intel-pill intel-pill-decayed">decayed</span>
                          : <span className="intel-muted">—</span>}</td>
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

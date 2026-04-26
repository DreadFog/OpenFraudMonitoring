import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "./api";
import FilterBuilder from "./FilterBuilder";
import "./Dashboard.css";

export default function Dashboard() {
  const [sessions, setSessions] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [schema, setSchema] = useState([]);
  const [filters, setFilters] = useState([]);
  const [connected, setConnected] = useState(true);
  const navigate = useNavigate();

  // Fetch schema once on mount
  useEffect(() => {
    api.getSchema().then(setSchema).catch(console.error);
  }, []);

  // Compute complete filters (all 3 fields filled)
  const completeFilters = filters.filter(
    (f) => f.field && f.op && f.value
  );

  // Fetch data — reacts to completed filter changes
  useEffect(() => {
    const load = async () => {
      try {
        const [sessionsData, statsData] = await Promise.all([
          api.getSessions(completeFilters),
          api.getStats(),
        ]);
        setSessions(sessionsData);
        setStats(statsData);
        setLoading(false);
        setConnected(true);
      } catch (err) {
        console.error(err);
        setSessions([]);
        setStats(null);
        setLoading(false);
        setConnected(false);
      }
    };

    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, [JSON.stringify(completeFilters)]);

  const clearFilters = () => {
    setFilters([]);
  };

  if (loading) {
    return <div className="container"><p>Loading...</p></div>;
  }

  return (
    <div className="container">
      {/* Header */}
      <header className="header">
        <h1>Anti-Fraud Fingerprint Dashboard</h1>
        <span className={`badge ${connected ? 'badge-live' : 'badge-offline'}`}>
          {connected ? 'LIVE' : 'OFFLINE'}
        </span>
        <button className="refresh-btn" onClick={() => setLoading(true)}>
          ↻ Refresh
        </button>
      </header>

      {/* Stats */}
      <div className="stats-grid">
        {stats && (
          <>
            <div className="stat">
              <div className="stat-num">{stats.total_sessions}</div>
              <div className="stat-label">Total Sessions</div>
            </div>
            <div className="stat">
              <div className="stat-num" style={{ color: "#f85149" }}>
                {stats.high_risk_count}
              </div>
              <div className="stat-label">High Risk</div>
            </div>
            <div className="stat">
              <div className="stat-num" style={{ color: "#f0883e" }}>
                {stats.bots_detected}
              </div>
              <div className="stat-label">Bots Detected</div>
            </div>
            <div className="stat">
              <div className="stat-num" style={{ color: "#3fb950" }}>
                {stats.low_risk_count}
              </div>
              <div className="stat-label">Low Risk</div>
            </div>
          </>
        )}
      </div>

      {/* Filters */}
      <FilterBuilder
        schema={schema}
        filters={filters}
        onChange={setFilters}
        onClear={clearFilters}
      />

      {/* Sessions Table */}
      <div className="table-wrapper">
        {sessions.length === 0 ? (
          <p className="empty-message">
            No sessions yet — load a page with fingerprint.js included.
          </p>
        ) : (
          <table className="sessions-table">
            <thead>
              <tr>
                <th>Device ID</th>
                <th>IP Address</th>
                <th>Risk Score</th>
                <th>Flags</th>
                <th>Device Type</th>
                <th>Language</th>
                <th>URLs Visited</th>
                <th>Heartbeats</th>
                <th>Last Seen</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((session) => {
                const riskClass =
                  session.risk_score >= 60
                    ? "risk-high"
                    : session.risk_score >= 30
                    ? "risk-med"
                    : "risk-low";

                const deviceType = session.is_mobile
                  ? "📱 Mobile"
                  : session.is_workstation
                  ? "💻 Workstation"
                  : "❓ Unknown";

                const timeSinceLastSeen = Math.round(
                  (Date.now() - session.last_seen) / 1000
                );
                const timeStr =
                  timeSinceLastSeen < 60
                    ? `${timeSinceLastSeen}s ago`
                    : `${Math.round(timeSinceLastSeen / 60)}m ago`;

                return (
                  <tr key={session.full_fsid} onClick={() => navigate(`/session/${session.full_fsid}`)}>
                    <td className="device-id">{session.fsid}</td>
                    <td>{session.client_ip}</td>
                    <td>
                      <span className={`risk-badge ${riskClass}`}>
                        {session.risk_score}
                      </span>
                    </td>
                    <td>
                      {session.flags.slice(0, 2).map((flag, i) => (
                        <span key={i} className="flag">
                          {flag.split(":")[0]}
                        </span>
                      ))}
                      {session.flags.length > 2 && (
                        <span className="flag">+{session.flags.length - 2}</span>
                      )}
                    </td>
                    <td>{deviceType}</td>
                    <td>{session.language}</td>
                    <td>{session.urls_count}</td>
                    <td>{session.heartbeats}</td>
                    <td className="time-ago">{timeStr}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

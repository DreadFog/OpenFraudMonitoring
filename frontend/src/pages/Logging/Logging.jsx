import React, { useEffect, useState, useCallback } from "react";
import { useAuth } from "../../AuthContext";
import { api } from "../../api";
import CorsSettings from "../../components/CorsSettings/CorsSettings";
import UserManagement from "../Users/Users";
import "./Logging.css";

const POLL_MS = 5000;

function fmtAge(seconds) {
  if (seconds == null) return "never";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

function fmtTs(ms) {
  if (!ms) return "";
  return new Date(ms).toISOString().replace("T", " ").slice(11, 19);
}

export default function Administration() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [status, setStatus] = useState(null);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState("");
  const [tail, setTail] = useState(100);

  const refresh = useCallback(async () => {
    try {
      const [s, l] = await Promise.all([
        api.getConnectorsStatus(),
        api.getConnectorsLogs(tail),
      ]);
      setStatus(s);
      setLogs(l.entries || []);
      setError("");
    } catch (err) {
      setError(err.message || "refresh failed");
    }
  }, [tail]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const connectors = status?.connectors || [];
  const queues = status?.queues || {};

  return (
    <div className="logging-page">
      <header className="logging-header">
        <h1>Administration</h1>
        <p className="logging-sub">Connector health, queue depths, recent warnings/errors, and system settings. Auto-refreshes every {POLL_MS / 1000}s.</p>
        <button className="logging-btn" type="button" onClick={refresh}>↻ Refresh now</button>
      </header>

      {error && <div className="logging-error">{error}</div>}

      {/* Queue depths */}
      <section className="logging-card">
        <h2>Queues</h2>
        <div className="logging-queues">
          <div className="queue-card">
            <div className="queue-name">ofm:events <span className="queue-sub">(real-time rules)</span></div>
            <div className="queue-depth">{queues.events ?? "—"}</div>
          </div>
          <div className="queue-card">
            <div className="queue-name">intel.responses <span className="queue-sub">(connector → backend)</span></div>
            <div className="queue-depth">{queues.responses ?? "—"}</div>
          </div>
          {connectors.map((c) => (
            <div className="queue-card" key={c.name}>
              <div className="queue-name">intel.requests.{c.name} <span className="queue-sub">(backend → {c.name})</span></div>
              <div className="queue-depth">{c.request_queue_depth ?? "—"}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Connector status */}
      <section className="logging-card">
        <h2>Connectors</h2>
        {connectors.length === 0 ? (
          <p className="logging-muted">No connectors registered.</p>
        ) : (
          <table className="logging-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Mode</th>
                <th>Last seen</th>
                <th>Request queue</th>
              </tr>
            </thead>
            <tbody>
              {connectors.map((c) => (
                <tr key={c.name}>
                  <td><b>{c.name}</b></td>
                  <td>
                    <span className={`status-pill ${c.healthy ? "status-healthy" : "status-unhealthy"}`}>
                      {c.healthy ? "● healthy" : "● unhealthy"}
                    </span>
                  </td>
                  <td>{c.mode}</td>
                  <td title={c.last_seen || ""}>{fmtAge(c.last_seen_age_seconds)}</td>
                  <td>{c.request_queue_depth ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Logs */}
      <section className="logging-card">
        <div className="logs-head">
          <h2>Recent logs</h2>
          <select className="logging-select" value={tail} onChange={(e) => setTail(Number(e.target.value))}>
            <option value={50}>last 50</option>
            <option value={100}>last 100</option>
            <option value={250}>last 250</option>
            <option value={500}>last 500</option>
          </select>
        </div>
        {logs.length === 0 ? (
          <p className="logging-muted">No log entries.</p>
        ) : (
          <div className="logs-list">
            {logs.map((l, i) => (
              <div key={i} className={`log-row log-${(l.level || "").toLowerCase()}`}>
                <span className="log-ts">{fmtTs(l.ts)}</span>
                <span className={`log-level log-level-${(l.level || "").toLowerCase()}`}>{l.level}</span>
                <span className="log-source">{l.source}</span>
                <span className="log-msg">{l.message}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {isAdmin && <CorsSettings />}

      {isAdmin && (
        <section className="logging-card">
          <UserManagement />
        </section>
      )}
    </div>
  );
}

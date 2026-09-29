import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../../api";
import FilterBuilder from "../../components/FilterBuilder/FilterBuilder";
import { usePersistentState } from "../../hooks/usePersistentState";
import "./Devices.css";

function confidenceClass(confidence) {
  if (confidence >= 0.9) return "confidence-high";
  if (confidence >= 0.75) return "confidence-med";
  return "confidence-low";
}

export default function Devices() {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(25);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [schema, setSchema] = useState([]);
  const [filters, setFilters] = usePersistentState("devices.filters", []);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (!location.state?.filters) return;
    setFilters(location.state.filters);
    setPage(1);
    navigate(location.pathname, { replace: true, state: null });
  }, [location.state]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    api.getDeviceSchema().then(setSchema).catch(() => setSchema([]));
  }, []);

  const completeKey = JSON.stringify(filters.filter((f) => f.field && f.op && f.value !== ""));
  const completeFilters = useMemo(() => JSON.parse(completeKey), [completeKey]);

  const loadDevices = useCallback(async () => {
    try {
      const result = await api.getDevices(page, perPage, completeFilters);
      setDevices(result.devices || []);
      setTotal(result.total || 0);
      setTotalPages(result.pages || 1);
    } catch (err) {
      console.error(err);
      setDevices([]);
    } finally {
      setLoading(false);
    }
  }, [page, perPage, completeFilters]);

  useEffect(() => {
    loadDevices();
    const interval = setInterval(loadDevices, 10000);
    return () => clearInterval(interval);
  }, [loadDevices]);

  const openDevice = (id) => navigate(`/device/${id}`);

  if (loading) {
    return <div className="container"><p>Loading...</p></div>;
  }

  return (
    <div className="container">
      <header className="page-header devices-header">
        <h1>Devices</h1>
        <p className="devices-subtitle">
          Device clusters resolved from stable hardware/OS signals, decoupled from the volatile fingerprint ID.
        </p>
      </header>

      <FilterBuilder
        schema={schema}
        filters={filters}
        onChange={(f) => { setFilters(f); setPage(1); }}
        onClear={() => { setFilters([]); setPage(1); }}
        suggest={api.getDeviceSuggestions}
      />

      <div className="table-wrapper">
        {devices.length === 0 ? (
          <p className="empty-message">
            {completeFilters.length > 0
              ? "No devices match the current filters."
              : "No devices yet — load a page with ofm.js included."}
          </p>
        ) : (
          <table className="sessions-table">
            <thead>
              <tr>
                <th>Device</th>
                <th>Type</th>
                <th>Platform</th>
                <th>GPU Renderer</th>
                <th>Confidence</th>
                <th>Sessions</th>
                <th>Distinct fsids</th>
                <th>Distinct IPs</th>
                <th>Last Seen</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((d) => (
                <tr
                  key={d.id}
                  onClick={() => openDevice(d.id)}
                  onAuxClick={(e) => {
                    if (e.button === 1) {
                      e.preventDefault();
                      window.open(`/device/${d.id}`, "_blank", "noopener");
                    }
                  }}
                  onMouseDown={(e) => { if (e.button === 1) e.preventDefault(); }}
                >
                  <td className="device-id">#{d.id} {d.cookie_id && <span title="Linked via client device UUID">🍪</span>}</td>
                  <td>{d.device_type === "mobile" ? "📱 Mobile" : d.device_type === "workstation" ? "💻 Workstation" : "❓ Unknown"}</td>
                  <td>{d.platform || "unknown"}</td>
                  <td>{d.webgl_renderer || "unknown"}</td>
                  <td><span className={`confidence-badge ${confidenceClass(d.confidence)}`}>{Math.round((d.confidence || 0) * 100)}%</span></td>
                  <td>{d.sessions_count}</td>
                  <td>{d.distinct_fsids}</td>
                  <td>{d.distinct_ips}</td>
                  <td className="time-ago">{d.last_seen ? new Date(d.last_seen).toLocaleString() : "unknown"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {total > 0 && (
        <div className="pagination-bar">
          <div className="pagination-info">
            Showing {Math.min((page - 1) * perPage + 1, total)}–{Math.min(page * perPage, total)} of {total} devices
          </div>
          <div className="pagination-controls">
            <button className="pagination-btn" disabled={page <= 1} onClick={() => setPage(1)} title="First page">«</button>
            <button className="pagination-btn" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} title="Previous page">‹</button>
            <span className="pagination-current">Page {page} / {totalPages}</span>
            <button className="pagination-btn" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} title="Next page">›</button>
            <button className="pagination-btn" disabled={page >= totalPages} onClick={() => setPage(totalPages)} title="Last page">»</button>
          </div>
          <select
            className="pagination-size-select"
            value={perPage}
            onChange={(e) => { setPerPage(Number(e.target.value)); setPage(1); }}
          >
            <option value={10}>10 per page</option>
            <option value={25}>25 per page</option>
            <option value={50}>50 per page</option>
            <option value={100}>100 per page</option>
          </select>
        </div>
      )}
    </div>
  );
}

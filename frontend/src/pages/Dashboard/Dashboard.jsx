import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { ResponsiveGridLayout, useContainerWidth } from "react-grid-layout";
import { api } from "../../api";
import FilterBuilder from "../../components/FilterBuilder/FilterBuilder";
import WidgetWizard from "../../components/WidgetWizard/WidgetWizard";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import "./Dashboard.css";

const GRID_COLS = 12;
const ROW_HEIGHT = 80;

const PALETTE = [
  "#58a6ff", "#f85149", "#f0883e", "#3fb950", "#bc8cff",
  "#79c0ff", "#d29922", "#ff7b72", "#56d364", "#e3b341",
];

const DEFAULT_WIDGETS = [
  { type: "stat", name: "Total Sessions", filters: [], field: null, limit: null, layout: { x: 0, y: 0, w: 2, h: 2 } },
  { type: "stat", name: "High Risk", filters: [{ field: "risk_score", op: "gte", value: "60" }], field: null, limit: null, layout: { x: 2, y: 0, w: 2, h: 2 } },
  { type: "stat", name: "Bots Detected", filters: [{ field: "fast_bot_detection", op: "eq", value: "true" }], field: null, limit: null, layout: { x: 4, y: 0, w: 2, h: 2 } },
  { type: "stat", name: "Low Risk", filters: [{ field: "risk_score", op: "lt", value: "30" }], field: null, limit: null, layout: { x: 6, y: 0, w: 2, h: 2 } },
];

const STAT_COLORS = {
  "Total Sessions": "#58a6ff",
  "High Risk": "#f85149",
  "Bots Detected": "#f0883e",
  "Low Risk": "#3fb950",
};

/* ── Pie chart (pure CSS conic-gradient) ── */
function PieChart({ groups }) {
  const total = groups.reduce((s, g) => s + g.count, 0);
  if (total === 0) return <p className="empty-note">No data</p>;

  let cumPct = 0;
  const stops = groups.map((g, i) => {
    const pct = (g.count / total) * 100;
    const start = cumPct;
    cumPct += pct;
    return `${PALETTE[i % PALETTE.length]} ${start}% ${cumPct}%`;
  });

  return (
    <div className="pie-wrapper">
      <div
        className="pie-circle"
        style={{ background: `conic-gradient(${stops.join(", ")})` }}
      />
      <div className="pie-legend">
        {groups.map((g, i) => (
          <div key={i} className="pie-legend-item">
            <span className="pie-swatch" style={{ background: PALETTE[i % PALETTE.length] }} />
            <span className="pie-legend-label">{g.value}</span>
            <span className="pie-legend-count">{g.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Histogram (horizontal bars) ── */
function Histogram({ groups }) {
  const max = Math.max(...groups.map((g) => g.count), 1);
  if (groups.length === 0) return <p className="empty-note">No data</p>;

  return (
    <div className="histogram">
      {groups.map((g, i) => (
        <div key={i} className="histo-row">
          <span className="histo-label">{g.value}</span>
          <div className="histo-bar-bg">
            <div
              className="histo-bar"
              style={{
                width: `${(g.count / max) * 100}%`,
                background: PALETTE[i % PALETTE.length],
              }}
            />
          </div>
          <span className="histo-count">{g.count}</span>
        </div>
      ))}
    </div>
  );
}

/* ── Weighted list ── */
function WeightedList({ groups }) {
  const max = Math.max(...groups.map((g) => g.count), 1);
  if (groups.length === 0) return <p className="empty-note">No data</p>;

  return (
    <div className="weighted-list">
      {groups.map((g, i) => (
        <div key={i} className="wl-item">
          <div className="wl-bar" style={{ width: `${(g.count / max) * 100}%` }} />
          <span className="wl-rank">{i + 1}.</span>
          <span className="wl-value">{g.value}</span>
          <span className="wl-count">{g.count}</span>
        </div>
      ))}
    </div>
  );
}

/* ── Default layout for new widget types ── */
function defaultLayout(type, index, existingWidgets) {
  const w = type === "stat" ? 2 : 4;
  const h = 2;
  // Place below existing widgets
  const maxY = existingWidgets.reduce((m, wd) => {
    const ly = wd.layout || { y: 0, h: 2 };
    return Math.max(m, (ly.y || 0) + (ly.h || 2));
  }, 0);
  return { x: 0, y: maxY, w, h };
}

/* ── Migrate legacy size field to layout ── */
function migrateWidget(widget, index) {
  if (widget.layout) return widget;
  const sizeMap = { small: 3, medium: 6, large: 9, full: 12 };
  const w = sizeMap[widget.size] || (widget.type === "stat" ? 3 : 6);
  const h = widget.type === "stat" ? 2 : 3;
  return { ...widget, layout: { x: (index * 3) % GRID_COLS, y: Math.floor((index * 3) / GRID_COLS) * h, w, h } };
}

/* ── Single widget card ── */
function WidgetCard({ widget, data, editMode, onEdit, onRemove }) {
  const renderContent = () => {
    if (!data) return <span className="widget-loading">…</span>;

    if (widget.type === "stat") {
      const color = STAT_COLORS[widget.name] || "#58a6ff";
      return <div className="stat-num" style={{ color }}>{data.count ?? "—"}</div>;
    }

    const groups = data.groups || [];
    if (widget.type === "pie") return <PieChart groups={groups} />;
    if (widget.type === "histogram") return <Histogram groups={groups} />;
    if (widget.type === "weighted_list") return <WeightedList groups={groups} />;
    return null;
  };

  return (
    <div className={`widget-card ${editMode ? "widget-edit-mode" : ""}`}>
      {editMode && (
        <div className="widget-toolbar">
          <button className="widget-tb-btn widget-tb-edit" onClick={onEdit} title="Edit widget">✎</button>
          <button className="widget-tb-btn widget-tb-delete" onClick={onRemove} title="Delete widget">×</button>
        </div>
      )}
      <div className="widget-content">{renderContent()}</div>
      <div className="stat-label">{widget.name}</div>
    </div>
  );
}

/* ── Main Dashboard ── */
export default function Dashboard() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [schema, setSchema] = useState([]);
  const [filters, setFilters] = useState([]);
  const [connected, setConnected] = useState(true);
  const navigate = useNavigate();
  const { containerRef, width: containerWidth } = useContainerWidth({ initialWidth: 1200 });

  // Dashboard state
  const [dashboards, setDashboards] = useState([]);
  const [currentDashboardId, setCurrentDashboardId] = useState(null);
  const [widgets, setWidgets] = useState(DEFAULT_WIDGETS);
  const [widgetData, setWidgetData] = useState({});
  const [showWizard, setShowWizard] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editingWidgetIndex, setEditingWidgetIndex] = useState(null);

  const isDefault = currentDashboardId === null;

  // Fetch schema + dashboards list on mount
  useEffect(() => {
    api.getSchema().then(setSchema).catch(console.error);
    api.getDashboards().then(setDashboards).catch(console.error);
  }, []);

  // Compute complete filters
  const completeFilters = filters.filter((f) => f.field && f.op && f.value);

  // Fetch sessions
  const loadSessions = useCallback(async () => {
    try {
      const sessionsData = await api.getSessions(completeFilters);
      setSessions(sessionsData);
      setLoading(false);
      setConnected(true);
    } catch (err) {
      console.error(err);
      setSessions([]);
      setLoading(false);
      setConnected(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(completeFilters)]);

  useEffect(() => {
    loadSessions();
    const interval = setInterval(loadSessions, 10000);
    return () => clearInterval(interval);
  }, [loadSessions]);

  // Fetch widget data whenever widgets change
  const loadWidgetData = useCallback(async () => {
    const results = {};
    await Promise.all(
      widgets.map(async (w, i) => {
        try {
          results[i] = await api.getWidgetData({
            type: w.type,
            field: w.field,
            filters: w.filters || [],
            limit: w.limit || 10,
          });
        } catch {
          results[i] = null;
        }
      })
    );
    setWidgetData(results);
  }, [widgets]);

  useEffect(() => {
    loadWidgetData();
    const interval = setInterval(loadWidgetData, 10000);
    return () => clearInterval(interval);
  }, [loadWidgetData]);

  // ── Dashboard management ──

  const loadDashboard = async (id) => {
    setEditMode(false);
    if (!id) {
      setCurrentDashboardId(null);
      setWidgets(DEFAULT_WIDGETS);
      return;
    }
    const db = dashboards.find((d) => d.id === id);
    if (db) {
      setCurrentDashboardId(id);
      setWidgets((db.widgets || []).map(migrateWidget));
    }
  };

  const saveDashboard = async () => {
    const name = window.prompt("Dashboard name:");
    if (!name?.trim()) return;
    try {
      const created = await api.createDashboard(name.trim(), widgets);
      setDashboards((prev) => [...prev, created]);
      setCurrentDashboardId(created.id);
    } catch (e) {
      alert(e.message || "Failed to save dashboard");
    }
  };

  const updateCurrentDashboard = async () => {
    if (!currentDashboardId) return;
    try {
      const updated = await api.updateDashboard(currentDashboardId, { widgets });
      setDashboards((prev) =>
        prev.map((d) => (d.id === updated.id ? updated : d))
      );
    } catch (e) {
      alert(e.message || "Failed to update dashboard");
    }
  };

  const deleteDashboard = async () => {
    if (!currentDashboardId) return;
    if (!window.confirm("Delete this saved dashboard?")) return;
    try {
      await api.deleteDashboard(currentDashboardId);
      setDashboards((prev) => prev.filter((d) => d.id !== currentDashboardId));
      setCurrentDashboardId(null);
      setWidgets(DEFAULT_WIDGETS);
    } catch (e) {
      alert(e.message || "Failed to delete dashboard");
    }
  };

  // ── Widget management ──

  const addWidget = (widget) => {
    if (!widget.layout) {
      widget.layout = defaultLayout(widget.type, widgets.length, widgets);
    }
    setWidgets((prev) => [...prev, widget]);
    setShowWizard(false);
    setEditingWidgetIndex(null);
  };

  const updateWidget = (widget) => {
    if (editingWidgetIndex !== null) {
      setWidgets((prev) => prev.map((w, i) => (i === editingWidgetIndex ? { ...widget, layout: w.layout } : w)));
    }
    setShowWizard(false);
    setEditingWidgetIndex(null);
  };

  const removeWidget = (index) => {
    setWidgets((prev) => prev.filter((_, i) => i !== index));
  };

  const openEditWidget = (index) => {
    setEditingWidgetIndex(index);
    setShowWizard(true);
  };

  // Build react-grid-layout layout array from widget data
  const buildLayout = () =>
    widgets.map((w, i) => {
      const ly = w.layout || defaultLayout(w.type, i, []);
      return { i: String(i), x: ly.x, y: ly.y, w: ly.w, h: ly.h, minW: 2, minH: 1 };
    });

  // When the user drags or resizes, persist layout back to widgets
  const handleLayoutChange = (newLayout) => {
    setWidgets((prev) =>
      prev.map((w, i) => {
        const item = newLayout.find((l) => l.i === String(i));
        if (!item) return w;
        return { ...w, layout: { x: item.x, y: item.y, w: item.w, h: item.h } };
      })
    );
  };

  const clearFilters = () => setFilters([]);

  if (loading) {
    return <div className="container"><p>Loading...</p></div>;
  }

  return (
    <div className={`container ${editMode ? "edit-mode" : ""}`}>
      {/* Header */}
      <header className="header">
        <h1>OpenFraudMonitoring Dashboard</h1>
        <span className={`badge ${connected ? 'badge-live' : 'badge-offline'}`}>
          {connected ? 'LIVE' : 'OFFLINE'}
        </span>
        <button className="refresh-btn" onClick={() => { loadSessions(); loadWidgetData(); }}>
          ↻ Refresh
        </button>
      </header>

      {/* Dashboard management bar */}
      <div className="dashboard-bar">
        <select
          className="dashboard-select"
          value={currentDashboardId ?? ""}
          onChange={(e) => loadDashboard(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">Default Dashboard</option>
          {dashboards.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
        <button className="dash-btn" onClick={saveDashboard}>Save As…</button>
        {currentDashboardId && (
          <>
            <button className="dash-btn" onClick={updateCurrentDashboard}>Update</button>
            <button className="dash-btn dash-btn-danger" onClick={deleteDashboard}>Delete</button>
          </>
        )}
        <div className="dashboard-bar-spacer" />
        {!isDefault && (
          <button
            className={`dash-btn ${editMode ? "dash-btn-edit-active" : ""}`}
            onClick={() => setEditMode((v) => !v)}
          >
            {editMode ? "✓ Done Editing" : "✎ Edit Mode"}
          </button>
        )}
      </div>

      {/* Widgets */}
      <div ref={containerRef}>
        <ResponsiveGridLayout
          className="widgets-grid"
          width={containerWidth}
          layouts={{ lg: buildLayout() }}
          breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480 }}
          cols={{ lg: 12, md: 8, sm: 4, xs: 2 }}
          rowHeight={ROW_HEIGHT}
          isDraggable={editMode && !isDefault}
          isResizable={editMode && !isDefault}

          onLayoutChange={handleLayoutChange}
        >
          {widgets.map((w, i) => (
            <div key={String(i)}>
              <WidgetCard
                widget={w}
                data={widgetData[i]}
                editMode={editMode && !isDefault}
                onEdit={() => openEditWidget(i)}
                onRemove={() => removeWidget(i)}
              />
            </div>
          ))}
        </ResponsiveGridLayout>
        {editMode && !isDefault && (
          <div className="widget-add-card" onClick={() => { setEditingWidgetIndex(null); setShowWizard(true); }}>
            <span className="widget-add-icon">+</span>
            <span className="widget-add-label">Add Widget</span>
          </div>
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

      {/* Widget Wizard Modal */}
      {showWizard && (
        <WidgetWizard
          schema={schema}
          onClose={() => { setShowWizard(false); setEditingWidgetIndex(null); }}
          onCreate={editingWidgetIndex !== null ? updateWidget : addWidget}
          initialWidget={editingWidgetIndex !== null ? widgets[editingWidgetIndex] : null}
        />
      )}
    </div>
  );
}

import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { ResponsiveGridLayout, useContainerWidth } from "react-grid-layout";
import { api } from "../../api";
import { usePersistentState } from "../../hooks/usePersistentState";
import FilterBuilder from "../../components/FilterBuilder/FilterBuilder";
import WidgetWizard from "../../components/WidgetWizard/WidgetWizard";
import IpIntelPopover from "../../components/IpIntelPopover/IpIntelPopover";
import { buildGraphUrl, sessionSeed } from "../Graph/graphLink";
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

/* ── Session row helpers ── */
function riskClassOf(score) {
  return score >= 60 ? "risk-high" : score >= 30 ? "risk-med" : "risk-low";
}

function deviceTypeLabel(s) {
  return s.is_mobile ? "📱 Mobile" : s.is_workstation ? "💻 Workstation" : "❓ Unknown";
}

function timeAgo(lastSeen) {
  const secs = Math.round((Date.now() - lastSeen) / 1000);
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.round(secs / 3600)}h ago`;
  return `${Math.round(secs / 86400)}d ago`;
}

/**
 * Group SUCCESSIVE sessions from the same IP: within an IP, a session joins the
 * current group when it starts less than an hour after the group's latest end.
 * Returns an array of groups ordered by most recent activity first.
 */
const ONE_HOUR_MS = 3600 * 1000;
function groupSuccessiveByIp(sessions) {
  const byIp = new Map();
  for (const s of sessions) {
    const ip = s.client_ip || "unknown";
    if (!byIp.has(ip)) byIp.set(ip, []);
    byIp.get(ip).push(s);
  }
  const groups = [];
  for (const [ip, list] of byIp) {
    const sorted = [...list].sort(
      (a, b) => (a.first_seen || a.last_seen) - (b.first_seen || b.last_seen)
    );
    let cur = null;
    for (const s of sorted) {
      const start = s.first_seen || s.last_seen;
      const end = s.last_seen || s.first_seen;
      if (cur && start - cur.end < ONE_HOUR_MS) {
        cur.sessions.push(s);
        cur.end = Math.max(cur.end, end);
        cur.maxScore = Math.max(cur.maxScore, s.risk_score || 0);
        cur.lastSeen = Math.max(cur.lastSeen, s.last_seen || 0);
        if ((s.last_seen || 0) >= cur.rep.last_seen) cur.rep = s;
      } else {
        cur = {
          ip,
          key: `${ip}:${start}`,
          sessions: [s],
          start,
          end,
          maxScore: s.risk_score || 0,
          lastSeen: s.last_seen || 0,
          rep: s,
        };
        groups.push(cur);
      }
    }
  }
  groups.sort((a, b) => b.lastSeen - a.lastSeen);
  return groups;
}

/* ── Main Dashboard ── */
export default function Dashboard() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [schema, setSchema] = useState([]);
  const [filters, setFilters] = usePersistentState("dashboard.filters", []);
  const [connected, setConnected] = useState(true);
  const [sortBy, setSortBy] = usePersistentState("dashboard.sortBy", "last_seen");
  const [sortOrder, setSortOrder] = usePersistentState("dashboard.sortOrder", "desc");
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = usePersistentState("dashboard.perPage", 10);
  const [totalSessions, setTotalSessions] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [selectedFsids, setSelectedFsids] = useState(() => new Set());
  const [groupByIp, setGroupByIp] = usePersistentState("dashboard.groupByIp", false);
  const [expandedGroups, setExpandedGroups] = useState(() => new Set());
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
      const result = await api.getSessions(completeFilters, sortBy, sortOrder, page, perPage);
      setSessions(result.sessions || []);
      setTotalSessions(result.total || 0);
      setTotalPages(result.pages || 1);
      setLoading(false);
      setConnected(true);
    } catch (err) {
      console.error(err);
      setSessions([]);
      setLoading(false);
      setConnected(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(completeFilters), sortBy, sortOrder, page, perPage]);

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

  const clearFilters = () => { setFilters([]); setPage(1); };

  const handleSort = (column) => {
    if (sortBy === column) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortBy(column);
      setSortOrder("desc");
    }
    setPage(1);
  };

  const renderSortIndicator = (column) => {
    if (sortBy !== column) return null;
    return sortOrder === "asc" ? " ▲" : " ▼";
  };

  const toggleSelected = (fsid) => {
    setSelectedFsids((prev) => {
      const next = new Set(prev);
      if (next.has(fsid)) next.delete(fsid);
      else next.add(fsid);
      return next;
    });
  };

  const allPageSelected = sessions.length > 0 && sessions.every((s) => selectedFsids.has(s.full_fsid));

  const toggleSelectAllPage = () => {
    setSelectedFsids((prev) => {
      const next = new Set(prev);
      if (allPageSelected) {
        sessions.forEach((s) => next.delete(s.full_fsid));
      } else {
        sessions.forEach((s) => next.add(s.full_fsid));
      }
      return next;
    });
  };

  const exploreSelectedInGraph = () => {
    const seeds = Array.from(selectedFsids).map((fsid) => sessionSeed(fsid));
    if (seeds.length === 0) return;
    navigate(buildGraphUrl(seeds));
  };

  const toggleGroupExpanded = (key) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleGroupSelected = (group) => {
    const fsids = group.sessions.map((s) => s.full_fsid);
    const allSelected = fsids.every((f) => selectedFsids.has(f));
    setSelectedFsids((prev) => {
      const next = new Set(prev);
      if (allSelected) fsids.forEach((f) => next.delete(f));
      else fsids.forEach((f) => next.add(f));
      return next;
    });
  };

  // Render a single session as a table row.
  const renderSessionRow = (session, isChild = false) => (
    <tr
      key={session.full_fsid}
      className={isChild ? "session-child-row" : ""}
      onClick={() => navigate(`/session/${session.full_fsid}`)}
      onAuxClick={(e) => {
        if (e.button === 1) {
          e.preventDefault();
          window.open(`/session/${session.full_fsid}`, "_blank", "noopener");
        }
      }}
      onMouseDown={(e) => { if (e.button === 1) e.preventDefault(); }}
    >
      <td className="select-col" onClick={(e) => e.stopPropagation()}>
        <input
          type="checkbox"
          checked={selectedFsids.has(session.full_fsid)}
          onChange={() => toggleSelected(session.full_fsid)}
        />
      </td>
      <td className="device-id">{isChild ? <span className="child-indent">↳ </span> : null}{session.fsid}</td>
      <td>{session.client_ip} <IpIntelPopover ip={session.client_ip} /></td>
      <td><span className={`risk-badge ${riskClassOf(session.risk_score)}`}>{session.risk_score}</span></td>
      <td>
        {session.flags.slice(0, 2).map((flag, i) => (
          <span key={i} className="flag">{flag.split(":")[0]}</span>
        ))}
        {session.flags.length > 2 && <span className="flag">+{session.flags.length - 2}</span>}
      </td>
      <td>{deviceTypeLabel(session)}</td>
      <td>{session.language}</td>
      <td>{session.urls_count}</td>
      <td>{session.heartbeats}</td>
      <td className="time-ago">{timeAgo(session.last_seen)}</td>
    </tr>
  );

  // Render an aggregated group row (multiple successive sessions from one IP).
  const renderGroupRow = (group) => {
    const expanded = expandedGroups.has(group.key);
    const fsids = group.sessions.map((s) => s.full_fsid);
    const allSelected = fsids.every((f) => selectedFsids.has(f));
    const flags = [...new Set(group.sessions.flatMap((s) => s.flags || []))];
    const urls = group.sessions.reduce((n, s) => n + (s.urls_count || 0), 0);
    const heartbeats = group.sessions.reduce((n, s) => n + (s.heartbeats || 0), 0);
    return (
      <tr key={group.key} className="session-group-row" onClick={() => toggleGroupExpanded(group.key)}>
        <td className="select-col" onClick={(e) => e.stopPropagation()}>
          <input type="checkbox" checked={allSelected} onChange={() => toggleGroupSelected(group)} />
        </td>
        <td className="device-id">
          <span className="group-caret">{expanded ? "▾" : "▸"}</span>
          {group.sessions.length} sessions
        </td>
        <td>{group.ip} <IpIntelPopover ip={group.ip} /></td>
        <td><span className={`risk-badge ${riskClassOf(group.maxScore)}`}>{group.maxScore}</span></td>
        <td>
          {flags.slice(0, 2).map((flag, i) => (
            <span key={i} className="flag">{flag.split(":")[0]}</span>
          ))}
          {flags.length > 2 && <span className="flag">+{flags.length - 2}</span>}
        </td>
        <td>{deviceTypeLabel(group.rep)}</td>
        <td>{group.rep.language}</td>
        <td>{urls}</td>
        <td>{heartbeats}</td>
        <td className="time-ago">{timeAgo(group.lastSeen)}</td>
      </tr>
    );
  };

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
          containerPadding={[24, 24]}
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
        onChange={(f) => { setFilters(f); setPage(1); }}
        onClear={clearFilters}
      />

      {/* Sessions Table */}
      <div className="table-wrapper">
        <div className="table-controls">
          <label className="group-toggle">
            <input
              type="checkbox"
              checked={groupByIp}
              onChange={(e) => setGroupByIp(e.target.checked)}
            />
            Group successive sessions by IP
          </label>
        </div>
        {selectedFsids.size > 0 && (
          <div className="selection-bar">
            <span className="selection-count">{selectedFsids.size} selected</span>
            <button className="dash-btn" onClick={exploreSelectedInGraph}>
              🕸 Explore in graph
            </button>
            <button className="dash-btn" onClick={() => setSelectedFsids(new Set())}>
              Clear selection
            </button>
          </div>
        )}
        {sessions.length === 0 ? (
          <p className="empty-message">
            No sessions yet — load a page with ofm.js included.
          </p>
        ) : (
          <table className="sessions-table">
            <thead>
              <tr>
                <th className="select-col">
                  <input
                    type="checkbox"
                    checked={allPageSelected}
                    onChange={toggleSelectAllPage}
                    title="Select all on this page"
                  />
                </th>
                <th>Device ID</th>
                <th>IP Address</th>
                <th>Risk Score</th>
                <th>Flags</th>
                <th 
                  className="sortable-header"
                  onClick={() => handleSort("device_type")}
                  title="Click to sort"
                >
                  Device Type{renderSortIndicator("device_type")}
                </th>
                <th>Language</th>
                <th>URLs Visited</th>
                <th>Heartbeats</th>
                <th 
                  className="sortable-header"
                  onClick={() => handleSort("last_seen")}
                  title="Click to sort"
                >
                  Last Seen{renderSortIndicator("last_seen")}
                </th>
              </tr>
            </thead>
            <tbody>
              {groupByIp
                ? groupSuccessiveByIp(sessions).flatMap((group) => {
                    if (group.sessions.length === 1) return [renderSessionRow(group.sessions[0])];
                    const rows = [renderGroupRow(group)];
                    if (expandedGroups.has(group.key)) {
                      rows.push(...group.sessions.map((s) => renderSessionRow(s, true)));
                    }
                    return rows;
                  })
                : sessions.map((session) => renderSessionRow(session))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalSessions > 0 && (
        <div className="pagination-bar">
          <div className="pagination-info">
            Showing {Math.min((page - 1) * perPage + 1, totalSessions)}–{Math.min(page * perPage, totalSessions)} of {totalSessions} sessions
          </div>
          <div className="pagination-controls">
            <button
              className="pagination-btn"
              disabled={page <= 1}
              onClick={() => setPage(1)}
              title="First page"
            >«</button>
            <button
              className="pagination-btn"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              title="Previous page"
            >‹</button>
            <span className="pagination-current">Page {page} / {totalPages}</span>
            <button
              className="pagination-btn"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              title="Next page"
            >›</button>
            <button
              className="pagination-btn"
              disabled={page >= totalPages}
              onClick={() => setPage(totalPages)}
              title="Last page"
            >»</button>
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

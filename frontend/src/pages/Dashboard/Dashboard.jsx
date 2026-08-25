import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { ResponsiveGridLayout, useContainerWidth } from "react-grid-layout";
import { api } from "../../api";
import { usePersistentState } from "../../hooks/usePersistentState";
import FilterBuilder from "../../components/FilterBuilder/FilterBuilder";
import WidgetWizard from "../../components/WidgetWizard/WidgetWizard";
import IpIntelPopover from "../../components/IpIntelPopover/IpIntelPopover";
import WidgetCard from "./widgets/WidgetCard";
import { buildGraphUrl, sessionSeed } from "../Graph/graphLink";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import "./Dashboard.css";

const GRID_COLS = 12;
const ROW_HEIGHT = 80;

const DEFAULT_WIDGETS = [
  { type: "stat", name: "Total Sessions", field: null, limit: null, layout: { x: 0, y: 0, w: 2, h: 2 } },
  { type: "stat", name: "High Risk", filters: [{ field: "risk_score", op: "gte", value: "60" }], field: null, limit: null, layout: { x: 2, y: 0, w: 2, h: 2 } },
  { type: "stat", name: "Bots Detected", filters: [{ field: "fast_bot_detection", op: "eq", value: "true" }], field: null, limit: null, layout: { x: 4, y: 0, w: 2, h: 2 } },
  { type: "stat", name: "Low Risk", filters: [{ field: "risk_score", op: "lt", value: "30" }], field: null, limit: null, layout: { x: 6, y: 0, w: 2, h: 2 } },
];

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

/* ── Session row helpers ── */
function riskClassOf(score) {
  return score >= 60 ? "risk-high" : score >= 30 ? "risk-med" : "risk-low";
}

function timeAgo(lastSeen) {
  const secs = Math.round((Date.now() - lastSeen) / 1000);
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.round(secs / 3600)}h ago`;
  return `${Math.round(secs / 86400)}d ago`;
}

/**
 * Group sessions that share the same resolved `device_id`. Sessions without
 * a device_id (not yet resolved, or from a private/ignored IP) are left
 * ungrouped. Returns an array of groups ordered by most recent activity first.
 */
function groupByDeviceId(sessions) {
  const byKey = new Map();
  let anonIndex = 0;
  for (const s of sessions) {
    const key = s.device_id != null ? `device:${s.device_id}` : `anon:${anonIndex++}`;
    if (!byKey.has(key)) byKey.set(key, []);
    byKey.get(key).push(s);
  }
  const groups = [];
  for (const [key, list] of byKey) {
    const lastSeen = Math.max(...list.map((s) => s.last_seen || 0));
    const maxScore = Math.max(...list.map((s) => s.risk_score || 0));
    const rep = list.reduce((best, s) => ((s.last_seen || 0) >= (best.last_seen || 0) ? s : best), list[0]);
    groups.push({ key, sessions: list, lastSeen, maxScore, rep, deviceId: list[0].device_id });
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
  const [sortBy, setSortBy] = usePersistentState("dashboard.sortBy", "last_seen");
  const [sortOrder, setSortOrder] = usePersistentState("dashboard.sortOrder", "desc");
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = usePersistentState("dashboard.perPage", 10);
  const [totalSessions, setTotalSessions] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [selectedFsids, setSelectedFsids] = useState(() => new Set());
  const [groupByDevice, setGroupByDevice] = usePersistentState("dashboard.groupByDevice", false);
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
    } catch (err) {
      console.error(err);
      setSessions([]);
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(completeFilters), sortBy, sortOrder, page, perPage]);

  useEffect(() => {
    loadSessions();
    const interval = setInterval(loadSessions, 10000);
    return () => clearInterval(interval);
  }, [loadSessions]);

  // Fetch widget data whenever widgets or global filters change
  const loadWidgetData = useCallback(async () => {
    const results = {};
    await Promise.all(
      widgets.map(async (w, i) => {
        try {
          results[i] = await api.getWidgetData({
            type: w.type,
            field: w.field,
            // Merge widget-level filters (e.g. default High Risk filter) with global filters
            filters: [...(w.filters || []), ...completeFilters],
            limit: w.limit || 10,
          });
        } catch {
          results[i] = null;
        }
      })
    );
    setWidgetData(results);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [widgets, JSON.stringify(completeFilters)]);

  useEffect(() => {
    loadWidgetData();
    const interval = setInterval(loadWidgetData, 10000);
    return () => clearInterval(interval);
  }, [loadWidgetData]);

  // ── Dashboard management ──

  const loadDashboard = async (value) => {
    if (value === "__new__") {
      const name = window.prompt("Dashboard name:");
      if (!name?.trim()) return;
      try {
        const created = await api.createDashboard(name.trim(), []);
        setDashboards((prev) => [...prev, created]);
        setCurrentDashboardId(created.id);
        setWidgets([]);
        setEditMode(true);
      } catch (e) {
        alert(e.message || "Failed to create dashboard");
      }
      return;
    }
    setEditMode(false);
    if (!value) {
      setCurrentDashboardId(null);
      setWidgets(DEFAULT_WIDGETS);
      return;
    }
    const id = Number(value);
    const db = dashboards.find((d) => d.id === id);
    if (db) {
      setCurrentDashboardId(id);
      setWidgets((db.widgets || []).map(migrateWidget));
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

  const handleEditToggle = async () => {
    if (editMode && currentDashboardId) {
      await updateCurrentDashboard();
    }
    setEditMode((v) => !v);
  };

  const deleteDashboard = async () => {
    if (!currentDashboardId) return;
    if (!window.confirm("Delete this saved dashboard?")) return;
    try {
      await api.deleteDashboard(currentDashboardId);
      setDashboards((prev) => prev.filter((d) => d.id !== currentDashboardId));
      setCurrentDashboardId(null);
      setWidgets(DEFAULT_WIDGETS);
      setEditMode(false);
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
      <td>{session.language}</td>
      <td>{session.urls_count}</td>
      <td>{session.heartbeats}</td>
      <td>{session.behavioral_events}</td>
      <td className="time-ago">{timeAgo(session.last_seen)}</td>
    </tr>
  );

  // Render an aggregated group row (multiple sessions sharing the same device_id).
  const renderGroupRow = (group) => {
    const expanded = expandedGroups.has(group.key);
    const fsids = group.sessions.map((s) => s.full_fsid);
    const allSelected = fsids.every((f) => selectedFsids.has(f));
    const flags = [...new Set(group.sessions.flatMap((s) => s.flags || []))];
    const urls = group.sessions.reduce((n, s) => n + (s.urls_count || 0), 0);
    const heartbeats = group.sessions.reduce((n, s) => n + (s.heartbeats || 0), 0);
    const behavioralEvents = group.sessions.reduce((n, s) => n + (s.behavioral_events || 0), 0);
    return (
      <tr key={group.key} className="session-group-row" onClick={() => toggleGroupExpanded(group.key)}>
        <td className="select-col" onClick={(e) => e.stopPropagation()}>
          <input type="checkbox" checked={allSelected} onChange={() => toggleGroupSelected(group)} />
        </td>
        <td className="device-id">
          <span className="group-caret">{expanded ? "▾" : "▸"}</span>
          {group.deviceId != null ? (
            <button
              className="device-link-btn"
              onClick={(e) => { e.stopPropagation(); navigate(`/device/${group.deviceId}`); }}
              title="View device"
            >
              Device #{group.deviceId}
            </button>
          ) : (
            `${group.sessions.length} sessions`
          )}
        </td>
        <td>{group.rep.client_ip} <IpIntelPopover ip={group.rep.client_ip} /></td>
        <td><span className={`risk-badge ${riskClassOf(group.maxScore)}`}>{group.maxScore}</span></td>
        <td>
          {flags.slice(0, 2).map((flag, i) => (
            <span key={i} className="flag">{flag.split(":")[0]}</span>
          ))}
          {flags.length > 2 && <span className="flag">+{flags.length - 2}</span>}
        </td>
        <td>{group.rep.language}</td>
        <td>{urls}</td>
        <td>{heartbeats}</td>
        <td>{behavioralEvents}</td>
        <td className="time-ago">{timeAgo(group.lastSeen)}</td>
      </tr>
    );
  };

  if (loading) {
    return <div className="container"><p>Loading...</p></div>;
  }

  return (
    <div className={`container ${editMode ? "edit-mode" : ""}`}>
      {/* Dashboard management bar */}
      <div className="dashboard-bar">
        <select
          className="dashboard-select"
          value={currentDashboardId ?? ""}
          disabled={editMode}
          onChange={(e) => loadDashboard(e.target.value)}
        >
          <option value="">Default Dashboard</option>
          {dashboards.map((d) => (
            <option key={d.id} value={String(d.id)}>{d.name}</option>
          ))}
          <option value="__new__">＋ New Dashboard…</option>
        </select>
        {currentDashboardId && !editMode && (
          <button className="dash-btn dash-btn-danger" onClick={deleteDashboard}>Delete</button>
        )}
        <div className="dashboard-bar-spacer" />
        {!isDefault && (
          <button
            className={`dash-btn ${editMode ? "dash-btn-edit-active" : ""}`}
            onClick={handleEditToggle}
          >
            {editMode ? "✓ Done Editing" : "✎ Edit Mode"}
          </button>
        )}
      </div>

      {/* Filters — above widgets, applies to both widgets and session table */}
      <FilterBuilder
        schema={schema}
        filters={filters}
        onChange={(f) => { setFilters(f); setPage(1); }}
        onClear={clearFilters}
      />

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

      {/* Sessions Table */}
      <div className="table-wrapper">
        <div className="table-controls">
          <label className="group-toggle">
            <input
              type="checkbox"
              checked={groupByDevice}
              onChange={(e) => setGroupByDevice(e.target.checked)}
            />
            Group by device
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
                <th>Fingerprint ID</th>
                <th>IP Address</th>
                <th>Risk Score</th>
                <th>Flags</th>
                <th>Language</th>
                <th>URLs Visited</th>
                <th>Heartbeats</th>
                <th>Behavioral Events</th>
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
              {groupByDevice
                ? groupByDeviceId(sessions).flatMap((group) => {
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

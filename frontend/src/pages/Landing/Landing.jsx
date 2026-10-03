import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../api";
import { useAuth } from "../../AuthContext";
import { usePersistentState } from "../../hooks/usePersistentState";
import { useRecentItems } from "../../hooks/useRecentItems";
import "./Landing.css";

const POLL_MS = 30000;
const DAY_MS = 24 * 60 * 60 * 1000;
const SNIPPET = '<script src="/ofm.js"></script>';

const RECENT_ICONS = { session: "👤", device: "💻", entity: "🔍", graph: "🕸" };

function relTime(ms) {
  if (!ms) return "";
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

function riskClass(score) {
  return score >= 60 ? "risk-high" : score >= 30 ? "risk-med" : "risk-low";
}

/* ── Quick search ── */

function QuickSearch() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [results, setResults] = useState(null);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) { setResults(null); return; }
    const timer = setTimeout(() => {
      api.overviewSearch(term).then(setResults).catch(() => setResults(null));
    }, 250);
    return () => clearTimeout(timer);
  }, [q]);

  useEffect(() => {
    const onDown = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const items = results ? [
    ...results.sessions.map((s) => ({
      key: `s:${s.id}`, icon: "👤", label: `Session #${s.id}`,
      sub: `${s.client_ip || "unknown IP"} · risk ${s.risk_score} · ${relTime(s.last_seen)}`,
      path: `/session/${s.id}`,
    })),
    ...results.devices.map((d) => ({
      key: `d:${d.id}`, icon: "💻", label: `Device #${d.id}`,
      sub: `${d.platform || "unknown platform"} · ${d.device_type}`, path: `/device/${d.id}`,
    })),
    ...results.entities.map((e) => ({
      key: `e:${e.type}:${e.value}`, icon: "🔍", label: e.name || e.value, sub: e.type,
      path: `/intelligence?type=${encodeURIComponent(e.type)}&value=${encodeURIComponent(e.value)}`,
    })),
  ] : [];

  const go = (path) => { setOpen(false); setQ(""); navigate(path); };

  return (
    <div className="lp-search" ref={wrapRef}>
      <input
        className="lp-search-input"
        type="search"
        value={q}
        placeholder="Search an IP, fsid, device ID, user agent…"
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && items.length > 0) go(items[0].path);
          if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && results && (
        <div className="lp-search-results">
          {items.length === 0 && <div className="lp-muted lp-search-empty">No matches.</div>}
          {items.map((it) => (
            <button type="button" key={it.key} className="lp-search-item" onMouseDown={() => go(it.path)}>
              <span className="lp-search-icon">{it.icon}</span>
              <span className="lp-search-text">
                <span className="lp-search-label">{it.label}</span>
                <span className="lp-muted">{it.sub}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Setup checklist ── */

function setupSteps(setup) {
  return [
    {
      done: setup.has_sessions,
      title: "Collect your first fingerprint",
      body: <>Add <code>{SNIPPET}</code> to a monitored page, or open the <a href="/demo.html" target="_blank" rel="noopener noreferrer">demo page</a>.</>,
      snippet: true,
    },
    {
      done: setup.active_origins > 0,
      title: "Allow collection origins (CORS)",
      body: "Only needed when the script runs on another origin than OFM.",
      path: "/admin/monitoring",
      optional: true,
    },
    {
      done: setup.active_domains > 0,
      title: "Configure a monitored domain",
      body: "Enables auth-cookie and login-attempt detection.",
      path: "/admin/monitoring",
      optional: true,
    },
    {
      done: setup.healthy_connectors > 0,
      title: "Run an enrichment connector",
      body: `${setup.healthy_connectors}/${setup.connectors} connector(s) healthy.`,
      path: "/admin",
      optional: true,
    },
    {
      done: setup.enabled_rules > 0,
      title: "Review detection rules",
      body: `${setup.enabled_rules} rule(s) enabled.`,
      path: "/rules",
    },
  ];
}

function SetupChecklist({ setup, isAdmin, compact, onDismiss }) {
  const steps = setupSteps(setup);
  const doneCount = steps.filter((s) => s.done).length;
  const copy = () => navigator.clipboard?.writeText(SNIPPET);
  return (
    <section className={`lp-card ${compact ? "" : "lp-setup-hero"}`}>
      <div className="lp-card-head">
        <h2>{compact ? "Setup" : "Get started with OpenFraudMonitoring"}</h2>
        <span className="lp-muted">{doneCount}/{steps.length} done</span>
        {compact && onDismiss && <button type="button" className="lp-link-btn" onClick={onDismiss}>Hide</button>}
      </div>
      <ol className="lp-steps">
        {steps.map((s) => (
          <li key={s.title} className={`lp-step ${s.done ? "lp-step-done" : ""}`}>
            <span className="lp-step-mark">{s.done ? "✓" : ""}</span>
            <div className="lp-step-body">
              <div className="lp-step-title">
                {s.title}{s.optional && <span className="lp-muted"> · optional</span>}
              </div>
              {!compact && <div className="lp-muted">{s.body}</div>}
              {!compact && s.snippet && !s.done && (
                <div className="lp-snippet">
                  <code>{SNIPPET}</code>
                  <button type="button" className="lp-link-btn" onClick={copy}>Copy</button>
                </div>
              )}
            </div>
            {isAdmin && s.path && !s.done && <Link to={s.path} className="lp-link-btn">Configure →</Link>}
          </li>
        ))}
      </ol>
    </section>
  );
}

/* ── Triage widgets ── */

function StatCard({ label, current, previous, onClick }) {
  const delta = current - previous;
  const Tag = onClick ? "button" : "div";
  return (
    <Tag type={onClick ? "button" : undefined} className={`lp-stat ${onClick ? "lp-stat-link" : ""}`} onClick={onClick}>
      <span className="lp-stat-label">{label}</span>
      <span className="lp-stat-value">{current}</span>
      <span className={`lp-stat-delta ${delta > 0 ? "lp-up" : delta < 0 ? "lp-down" : ""}`}>
        {delta > 0 ? "▲" : delta < 0 ? "▼" : "•"} {delta > 0 ? `+${delta}` : delta} vs previous 24h
      </span>
    </Tag>
  );
}

function Sparkline({ values }) {
  const max = Math.max(1, ...values);
  return (
    <div className="lp-spark" title="Matches per hour, last 24h">
      {values.map((v, i) => (
        <span key={i} className="lp-spark-bar" style={{ height: `${Math.max(v ? 12 : 4, (v / max) * 100)}%`, opacity: v ? 1 : 0.3 }} />
      ))}
    </div>
  );
}

function HealthCard() {
  const [status, setStatus] = useState(null);
  const [logCounts, setLogCounts] = useState({ errors: 0, warnings: 0 });

  const load = useCallback(() => {
    api.getConnectorsStatus().then(setStatus).catch(() => setStatus(null));
    api.getConnectorsLogs(500).then((r) => {
      const since = Date.now() - DAY_MS;
      const recent = (r.entries || []).filter((l) => (l.ts || 0) >= since);
      const level = (l) => String(l.level || "").toUpperCase();
      setLogCounts({
        errors: recent.filter((l) => level(l) === "ERROR" || level(l) === "CRITICAL").length,
        warnings: recent.filter((l) => level(l) === "WARNING").length,
      });
    }).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const connectors = status?.connectors || [];
  const healthy = connectors.filter((c) => c.healthy).length;
  return (
    <section className="lp-card">
      <div className="lp-card-head">
        <h2>Platform health</h2>
        <Link to="/admin" className="lp-link-btn">Logs →</Link>
      </div>
      <div className="lp-health-grid">
        <div className={`lp-health-item ${connectors.length && healthy < connectors.length ? "lp-bad" : "lp-good"}`}>
          <span className="lp-health-value">{healthy}/{connectors.length}</span>
          <span className="lp-muted">connectors healthy</span>
        </div>
        <div className="lp-health-item">
          <span className="lp-health-value">{status?.queues?.events ?? "—"}</span>
          <span className="lp-muted">events queued</span>
        </div>
        <div className={`lp-health-item ${logCounts.errors ? "lp-bad" : "lp-good"}`}>
          <span className="lp-health-value">{logCounts.errors}</span>
          <span className="lp-muted">errors (24h)</span>
        </div>
        <div className={`lp-health-item ${logCounts.warnings ? "lp-warn" : ""}`}>
          <span className="lp-health-value">{logCounts.warnings}</span>
          <span className="lp-muted">warnings (24h)</span>
        </div>
      </div>
      {connectors.length > 0 && (
        <div className="lp-connectors">
          {connectors.map((c) => (
            <span key={c.name} className={`lp-pill ${c.healthy ? "lp-good" : "lp-bad"}`}>● {c.name}</span>
          ))}
        </div>
      )}
    </section>
  );
}

/* ── Page ── */

export default function Landing() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.role === "admin";
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState("");
  const [recent] = useRecentItems();
  const [setupHidden, setSetupHidden] = usePersistentState("landing.setupHidden", false);

  useEffect(() => {
    const load = () => api.getOverview().then((d) => { setOverview(d); setError(""); }).catch((e) => setError(e.message));
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, []);

  const toDashboard = (filters) => navigate("/dashboard", { state: { filters, timeRange: { mode: "24h" } } });
  const setup = overview?.setup;
  const firstRun = setup && !setup.has_sessions;
  const setupIncomplete = setup && setupSteps(setup).some((s) => !s.done);

  return (
    <div className="lp">
      <header className="lp-header">
        <div className="lp-title">
          <img src="/logo.png" alt="" className="lp-logo" />
          <div>
            <h1>{user ? `Welcome back, ${user.username}` : "OpenFraudMonitoring"}</h1>
            <p className="lp-muted">What needs your attention in the last 24 hours.</p>
          </div>
        </div>
        <QuickSearch />
      </header>

      {error && <div className="lp-error">{error}</div>}
      {!overview && !error && <p className="lp-muted">Loading…</p>}

      {firstRun && <SetupChecklist setup={setup} isAdmin={isAdmin} />}

      {overview && !firstRun && (
        <>
          <div className="lp-stats">
            <StatCard label="Active sessions" current={overview.current.sessions} previous={overview.previous.sessions} onClick={() => toDashboard([])} />
            <StatCard
              label="High risk"
              current={overview.current.high_risk}
              previous={overview.previous.high_risk}
              onClick={() => toDashboard([{ field: "risk_score", op: "gte", value: "60" }])}
            />
            <StatCard label="Bots detected" current={overview.current.bots} previous={overview.previous.bots} />
            <StatCard
              label="New devices"
              current={overview.current.new_devices}
              previous={overview.previous.new_devices}
              onClick={() => navigate("/devices", { state: { filters: [{ field: "first_seen", op: "gte", value: String(Date.now() - DAY_MS) }] } })}
            />
          </div>

          <div className="lp-grid">
            <section className="lp-card">
              <div className="lp-card-head">
                <h2>Needs review</h2>
                <span className="lp-muted">risk ≥ 60, last 24h</span>
              </div>
              {overview.review.length === 0 ? (
                <p className="lp-muted">Nothing high-risk in the last 24 hours. 🎉</p>
              ) : (
                <ul className="lp-list">
                  {overview.review.map((s) => (
                    <li key={s.id}>
                      <Link to={`/session/${s.id}`} className="lp-row">
                        <span className={`lp-risk ${riskClass(s.risk_score)}`}>{s.risk_score}</span>
                        <span className="lp-row-main">
                          <span className="lp-row-title">{s.client_ip || "unknown IP"}</span>
                          <span className="lp-flags">
                            {s.flags.slice(0, 3).map((f) => <span key={f} className="lp-flag">{String(f).split(":")[0]}</span>)}
                            {s.flags.length > 3 && <span className="lp-flag">+{s.flags.length - 3}</span>}
                          </span>
                        </span>
                        <span className="lp-muted lp-row-time">{relTime(s.last_seen)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="lp-card">
              <div className="lp-card-head">
                <h2>Rule activity</h2>
                <span className="lp-muted">last 24h</span>
              </div>
              {overview.rules.length === 0 ? (
                <p className="lp-muted">No rule matched in the last 24 hours.</p>
              ) : (
                <ul className="lp-list">
                  {overview.rules.map((r) => (
                    <li key={r.rule_id}>
                      <button type="button" className="lp-row" onClick={() => toDashboard([{ field: "triggered_flag", op: "eq", value: r.name }])}>
                        <span className="lp-row-main">
                          <span className="lp-row-title">
                            {r.name}
                            {r.spike && <span className="lp-spike" title="At least twice the previous 24h">spike</span>}
                          </span>
                          <span className="lp-muted">{r.current} match{r.current > 1 ? "es" : ""} · {r.previous} previous 24h</span>
                        </span>
                        <Sparkline values={r.hourly} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {isAdmin && <HealthCard />}

            <section className="lp-card">
              <div className="lp-card-head">
                <h2>Recently viewed</h2>
              </div>
              {recent.length === 0 ? (
                <p className="lp-muted">Sessions, devices, intel entities and graphs you open will appear here.</p>
              ) : (
                <ul className="lp-list">
                  {recent.map((it) => (
                    <li key={it.key}>
                      <Link to={it.path} className="lp-row">
                        <span className="lp-recent-icon">{RECENT_ICONS[it.kind] || "•"}</span>
                        <span className="lp-row-main">
                          <span className="lp-row-title">{it.label}</span>
                          <span className="lp-muted lp-ellipsis">{it.sub}</span>
                        </span>
                        <span className="lp-muted lp-row-time">{relTime(it.ts)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {isAdmin && setupIncomplete && !setupHidden && (
              <SetupChecklist setup={setup} isAdmin compact onDismiss={() => setSetupHidden(true)} />
            )}
          </div>
        </>
      )}
    </div>
  );
}

import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../../api";
import IpIntelPopover from "../../components/IpIntelPopover/IpIntelPopover";
import { buildGraphUrl, sessionSeed } from "../Graph/graphLink";
import "./SessionDetail.css";

function Field({ label, value, popoverIp }) {
  if (value === null || value === undefined) return null;
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <span className="field-value">{String(value)}{popoverIp && <IpIntelPopover ip={popoverIp} />}</span>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="sd-section">
      <h3 className="sd-section-title">{title}</h3>
      <div className="sd-section-body">{children}</div>
    </div>
  );
}

function RawJson({ data }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="sd-section">
      <button className="toggle-btn" onClick={() => setOpen(o => !o)}>
        {open ? "Hide" : "Show"} raw JSON
      </button>
      {open && (
        <pre className="json-viewer">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

/* ── Session timeline ── */

const EVENT_META = {
  button_click: { icon: "🖱", label: "Button click" },
  form_submit: { icon: "📝", label: "Form submit" },
  copy: { icon: "📋", label: "Copy" },
  paste: { icon: "📎", label: "Paste" },
};

function eventMeta(type) {
  return EVENT_META[type] || { icon: "•", label: (type || "event").replace(/_/g, " ") };
}

function fmtTime(ms) {
  if (!ms) return "—";
  return new Date(ms).toLocaleTimeString();
}

function fmtFull(ms) {
  if (!ms) return "—";
  return new Date(ms).toLocaleString();
}

/**
 * Build a timeline grouped into "visit" boxes (a contiguous run of events that
 * share the same URL). Within each box, consecutive heartbeats are collapsed
 * into a single aggregated item carrying the first/last time and summed counts.
 */
function buildTimeline(heartbeats, events) {
  const items = [
    ...(heartbeats || []).map((h) => ({ kind: "heartbeat", timestamp: h.timestamp, url: h.url || "", hb: h })),
    ...(events || []).map((e) => ({ kind: "event", timestamp: e.timestamp, url: e.url || "", event: e })),
  ].sort((a, b) => a.timestamp - b.timestamp);

  const boxes = [];
  let cur = null;
  for (const it of items) {
    if (!cur || cur.url !== it.url) {
      cur = { url: it.url, start: it.timestamp, end: it.timestamp, items: [] };
      boxes.push(cur);
    }
    cur.end = it.timestamp;
    cur.items.push(it);
  }

  for (const box of boxes) {
    const agg = [];
    let run = null;
    for (const it of box.items) {
      if (it.kind === "heartbeat") {
        if (!run) {
          run = {
            kind: "heartbeat_group",
            first: it.timestamp,
            last: it.timestamp,
            count: 0,
            sums: { mouseMoves: 0, clicks: 0, keydowns: 0, scrolls: 0, touches: 0 },
          };
          agg.push(run);
        }
        run.last = it.timestamp;
        run.count += 1;
        run.sums.mouseMoves += it.hb.mouseMoves || 0;
        run.sums.clicks += it.hb.clicks || 0;
        run.sums.keydowns += it.hb.keydowns || 0;
        run.sums.scrolls += it.hb.scrolls || 0;
        run.sums.touches += it.hb.touches || 0;
      } else {
        run = null;
        agg.push(it);
      }
    }
    box.agg = agg;
  }
  return boxes;
}

function DetailRow({ k, v }) {
  return (
    <div className="tl-detail-row">
      <span className="tl-detail-key">{k}</span>
      <span className="tl-detail-val">{v}</span>
    </div>
  );
}

function TimelineItem({ item }) {
  const [open, setOpen] = useState(false);

  if (item.kind === "heartbeat_group") {
    const label = item.count > 1 ? `${item.count} heartbeats` : "Heartbeat";
    return (
      <div className="tl-item tl-item--heartbeat">
        <button className="tl-item-head" onClick={() => setOpen((o) => !o)}>
          <span className="tl-dot" />
          <span className="tl-item-label">🫀 {label}</span>
          <span className="tl-item-time">
            {fmtTime(item.first)}{item.count > 1 ? ` – ${fmtTime(item.last)}` : ""}
          </span>
          <span className="tl-caret">{open ? "▾" : "▸"}</span>
        </button>
        {open && (
          <div className="tl-item-detail">
            <DetailRow k="Heartbeats" v={item.count} />
            <DetailRow k="First" v={fmtFull(item.first)} />
            <DetailRow k="Last" v={fmtFull(item.last)} />
            <DetailRow k="Mouse moves" v={item.sums.mouseMoves} />
            <DetailRow k="Clicks" v={item.sums.clicks} />
            <DetailRow k="Keydowns" v={item.sums.keydowns} />
            <DetailRow k="Scrolls" v={item.sums.scrolls} />
            <DetailRow k="Touches" v={item.sums.touches} />
          </div>
        )}
      </div>
    );
  }

  const e = item.event;
  const meta = eventMeta(e.event_type);
  const details = Object.entries(e.data || {});
  return (
    <div className={`tl-item tl-item--${e.event_type}`}>
      <button className="tl-item-head" onClick={() => setOpen((o) => !o)}>
        <span className="tl-dot" />
        <span className="tl-item-label">{meta.icon} {meta.label}</span>
        <span className="tl-item-time">{fmtTime(e.timestamp)}</span>
        <span className="tl-caret">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="tl-item-detail">
          <DetailRow k="Time" v={fmtFull(e.timestamp)} />
          {details.map(([k, v]) => (
            <DetailRow key={k} k={k} v={typeof v === "object" ? JSON.stringify(v) : String(v)} />
          ))}
          {details.length === 0 && <div className="tl-empty">No additional details.</div>}
        </div>
      )}
    </div>
  );
}

function SessionTimeline({ heartbeats, events }) {
  const boxes = buildTimeline(heartbeats, events);
  const total = (heartbeats?.length || 0) + (events?.length || 0);

  return (
    <div className="sd-section sd-timeline-section">
      <h3 className="sd-section-title">Activity Timeline ({total} events)</h3>
      {boxes.length === 0 ? (
        <p className="empty-note">No activity recorded.</p>
      ) : (
        <div className="timeline">
          {boxes.map((box, i) => (
            <div className="tl-box" key={i}>
              <div className="tl-box-head">
                <span className="tl-url" title={box.url || "(no URL)"}>{box.url || "(no URL)"}</span>
                <span className="tl-range">{fmtTime(box.start)} – {fmtTime(box.end)}</span>
              </div>
              <div className="tl-items">
                {box.agg.map((it, j) => (
                  <TimelineItem item={it} key={j} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function SessionDetail() {
  const { fsid } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [ruleDescriptions, setRuleDescriptions] = useState({});
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    if (!window.confirm("Delete this session and all its data? This cannot be undone.")) return;
    setDeleting(true);
    try {
      await api.deleteSession(fsid);
      navigate("/");
    } catch (e) {
      alert("Failed to delete session.");
      setDeleting(false);
    }
  };

  useEffect(() => {
    api.getSessionDetail(fsid)
      .then(setData)
      .catch(() => setError("Failed to load session."));
    api.getRules()
      .then((rules) => {
        const map = {};
        for (const r of rules) {
          map[r.name] = r.description || "";
        }
        setRuleDescriptions(map);
      })
      .catch(() => {});
  }, [fsid]);

  if (error) {
    return (
      <div className="sd-container">
        <p className="sd-error">{error}</p>
        <button className="back-btn" onClick={() => navigate("/")}>Back</button>
      </div>
    );
  }

  if (!data) {
    return <div className="sd-container"><p className="sd-loading">Loading…</p></div>;
  }

  const fp = data.latest_fingerprint || {};
  const sig = fp.signals || {};
  const auto = sig.automation || {};
  const device = sig.device || {};
  const scr = device.screenResolution || {};
  const media = device.multimediaDevices || {};
  const mq = device.mediaQueries || {};
  const browser = sig.browser || {};
  const hev = browser.highEntropyValues || {};
  const plugins = browser.plugins || {};
  const gfx = sig.graphics || {};
  const gl = gfx.webGL || {};
  const gpu = gfx.webgpu || {};
  const canvas = gfx.canvas || {};
  const codecs = sig.codecs || {};
  const locale = sig.locale || {};
  const intl = locale.internationalization || {};
  const langs = locale.languages || {};
  const contexts = sig.contexts || {};
  const ext = fp._extensions || {};
  const ipExt = ext.ip || {};
  const botDetails = fp.fastBotDetectionDetails || {};

  const riskClass =
    data.risk_score >= 60 ? "risk-high" : data.risk_score >= 30 ? "risk-med" : "risk-low";

  // Collect triggered detections
  const detections = Object.entries(botDetails)
    .filter(([, v]) => v && v.detected)
    .map(([name, v]) => ({ name, severity: v.severity || "low" }));

  return (
    <div className="sd-container">
      {/* Header */}
      <header className="sd-header">
        <button className="back-btn" onClick={() => navigate("/")}>← Back</button>
        <h1>Session Detail</h1>
        <span className={`risk-badge ${riskClass}`}>{data.risk_score}</span>
        <button className="graph-explore-btn" onClick={() => navigate(buildGraphUrl([sessionSeed(data.fsid)]))}>
          🕸 Explore in graph
        </button>
        <button className="delete-btn" onClick={handleDelete} disabled={deleting}>
          {deleting ? "Deleting…" : "🗑 Delete"}
        </button>
      </header>

      <div className="sd-body sd-body--split">
        <div className="sd-col-left">
        {/* Overview */}
        <Section title="Overview">
          <Field label="Fingerprint ID (fsid)" value={data.fsid} />
          <Field label="Client IP"    value={data.client_ip} popoverIp={data.client_ip} />
          <Field label="Public IP"    value={ipExt.ip} popoverIp={ipExt.ip} />
          <Field label="Country"      value={ipExt.country} />
          <Field label="City"         value={ipExt.city} />
          <Field label="Bot Detected" value={fp.fastBotDetection ? "YES" : "No"} />
          <Field label="Risk Score"   value={data.risk_score} />
          <Field label="First Seen"   value={new Date(data.first_seen).toLocaleString()} />
          <Field label="Last Seen"    value={new Date(data.last_seen).toLocaleString()} />
          <Field label="Fingerprints" value={data.fingerprints_count} />
          <Field label="Heartbeats"   value={data.heartbeats_count} />
          <Field label="Behavioral Events" value={data.behavioral_events_count} />
        </Section>

        {/* Risk Flags */}
        {data.flags.length > 0 && (
          <Section title={`Risk Flags (${data.flags.length})`}>
            <div className="flags-detail-list">
              {data.flags.map((flag, i) => (
                <div key={i} className="flag-detail-item">
                  <span className="flag-item">{flag}</span>
                  {ruleDescriptions[flag] && (
                    <span className="flag-description">{ruleDescriptions[flag]}</span>
                  )}
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Browser */}
        <Section title="Browser">
          <Field label="User Agent"           value={browser.userAgent} />
          <Field label="Platform"             value={device.platform} />
          <Field label="Architecture"         value={hev.architecture} />
          <Field label="Bitness"              value={hev.bitness} />
          <Field label="Platform Version"     value={hev.platformVersion} />
          <Field label="Mobile"               value={hev.mobile === true ? "Yes" : hev.mobile === false ? "No" : hev.mobile ?? "NA"} />
          <Field label="Model"                value={hev.model} />
          <Field label="Language"             value={langs.language} />
          <Field label="Languages"            value={Array.isArray(langs.languages) ? langs.languages.join(", ") : null} />
          <Field label="CPU Cores"            value={device.cpuCount} />
          <Field label="Device Memory (GB)"   value={device.memory} />
        </Section>

        {/* Screen */}
        <Section title="Screen">
          <Field label="Resolution"       value={scr.width && scr.height ? `${scr.width} × ${scr.height}` : null} />
          <Field label="Available"        value={scr.availableWidth && scr.availableHeight ? `${scr.availableWidth} × ${scr.availableHeight}` : null} />
          <Field label="Inner Window"     value={scr.innerWidth && scr.innerHeight ? `${scr.innerWidth} × ${scr.innerHeight}` : null} />
          <Field label="Color Depth"      value={scr.colorDepth} />
          <Field label="Pixel Depth"      value={scr.pixelDepth} />
          <Field label="Multiple Displays" value={scr.hasMultipleDisplays ? "Yes" : "No"} />
          <Field label="Color Scheme"     value={mq.prefersColorScheme} />
          <Field label="Pointer"          value={mq.pointer} />
          <Field label="Hover"            value={mq.hover ? "Yes" : "No"} />
        </Section>

        {/* Timezone & Locale */}
        <Section title="Timezone & Locale">
          <Field label="Timezone"         value={intl.timezone} />
          <Field label="Locale Language"  value={intl.localeLanguage} />
          <Field label="ETSL"             value={browser.etsl} />
        </Section>

        {/* Graphics */}
        <Section title="Graphics">
          <Field label="WebGL Vendor"     value={gl.vendor} />
          <Field label="WebGL Renderer"   value={gl.renderer} />
          <Field label="WebGPU Vendor"    value={gpu.vendor} />
          <Field label="WebGPU Device"    value={gpu.device} />
          <Field label="WebGPU Arch"      value={gpu.architecture} />
          <Field label="Canvas Fingerprint" value={canvas.canvasFingerprint} />
          <Field label="Canvas Modified"  value={canvas.hasModifiedCanvas ? "Yes" : "No"} />
        </Section>

        {/* Codecs */}
        <Section title="Codecs">
          <Field label="Audio CanPlayType" value={codecs.audioCanPlayTypeHash} />
          <Field label="Video CanPlayType" value={codecs.videoCanPlayTypeHash} />
          <Field label="MediaSource"       value={codecs.hasMediaSource ? "Yes" : "No"} />
        </Section>

        {/* Plugins & Extensions */}
        <Section title="Plugins & Extensions">
          <Field label="Plugin Count"      value={plugins.pluginCount} />
          <Field label="Valid Plugin Array" value={plugins.isValidPluginArray ? "Yes" : "No"} />
          <Field label="Plugin Names Hash" value={plugins.pluginNamesHash} />
          <Field label="Extensions"        value={browser.extensions?.bitmask} />
        </Section>

        {/* Automation Signals */}
        <Section title="Automation Signals">
          <Field label="WebDriver"         value={auto.webdriver ? "DETECTED" : "No"} />
          <Field label="Selenium"          value={auto.selenium ? "DETECTED" : "No"} />
          <Field label="CDP"               value={auto.cdp ? "DETECTED" : "No"} />
          <Field label="Playwright"        value={auto.playwright ? "DETECTED" : "No"} />
          <Field label="WebDriver Writable" value={auto.webdriverWritable ? "DETECTED" : "No"} />
        </Section>

        {/* Bot Detections (FPScanner) */}
        <Section title={`Bot Detections (${detections.length})`}>
          {detections.length === 0 ? (
            <p className="empty-note">No bot signals detected.</p>
          ) : (
            <div className="flags-list">
              {detections.map((d, i) => (
                <span key={i} className={`flag-item severity-${d.severity}`}>{d.name} ({d.severity})</span>
              ))}
            </div>
          )}
        </Section>

        {/* Cross-context checks */}
        {(contexts.iframe || contexts.webWorker) && (
          <Section title="Cross-Context Checks">
            {contexts.iframe && (
              <>
                <Field label="Iframe WebDriver"  value={contexts.iframe.webdriver ? "DETECTED" : "No"} />
                <Field label="Iframe Platform"    value={contexts.iframe.platform} />
                <Field label="Iframe CPU"         value={contexts.iframe.cpuCount} />
              </>
            )}
            {contexts.webWorker && (
              <>
                <Field label="Worker WebDriver"   value={contexts.webWorker.webdriver ? "DETECTED" : "No"} />
                <Field label="Worker Platform"     value={contexts.webWorker.platform} />
                <Field label="Worker WebGL Vendor" value={contexts.webWorker.vendor} />
                <Field label="Worker WebGL Renderer" value={contexts.webWorker.renderer} />
              </>
            )}
          </Section>
        )}

        {/* Multimedia Devices */}
        <Section title="Multimedia Devices">
          <Field label="Speakers"      value={media.speakers} />
          <Field label="Microphones"   value={media.microphones} />
          <Field label="Webcams"       value={media.webcams} />
        </Section>

          {/* Raw JSON */}
          <RawJson data={data} />
        </div>

        <div className="sd-col-right">
          <SessionTimeline heartbeats={data.heartbeats} events={data.behavioral_events} />
        </div>
      </div>
    </div>
  );
}

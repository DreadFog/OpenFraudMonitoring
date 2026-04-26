import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "./api";
import "./SessionDetail.css";

function Field({ label, value }) {
  if (value === null || value === undefined) return null;
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <span className="field-value">{String(value)}</span>
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

export default function SessionDetail() {
  const { fsid } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getSessionDetail(fsid)
      .then(setData)
      .catch(() => setError("Failed to load session."));
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
      </header>

      <div className="sd-body">
        {/* Overview */}
        <Section title="Overview">
          <Field label="Fingerprint ID (fsid)" value={data.fsid} />
          <Field label="Client IP"    value={data.client_ip} />
          <Field label="Public IP"    value={ipExt.ip} />
          <Field label="Country"      value={ipExt.country} />
          <Field label="City"         value={ipExt.city} />
          <Field label="Bot Detected" value={fp.fastBotDetection ? "YES" : "No"} />
          <Field label="Risk Score"   value={data.risk_score} />
          <Field label="First Seen"   value={new Date(data.first_seen).toLocaleString()} />
          <Field label="Last Seen"    value={new Date(data.last_seen).toLocaleString()} />
          <Field label="Fingerprints" value={data.fingerprints_count} />
          <Field label="Heartbeats"   value={data.heartbeats_count} />
        </Section>

        {/* Risk Flags */}
        {data.flags.length > 0 && (
          <Section title={`Risk Flags (${data.flags.length})`}>
            <div className="flags-list">
              {data.flags.map((flag, i) => (
                <span key={i} className="flag-item">{flag}</span>
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
          <Field label="Mobile"               value={hev.mobile ? "Yes" : "No"} />
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

        {/* URLs Visited */}
        <Section title={`URLs Visited (${(data.urls || []).length})`}>
          {(data.urls || []).length === 0 ? (
            <p className="empty-note">No URLs recorded.</p>
          ) : (
            <div className="urls-list">
              {(data.urls || []).map((url, i) => (
                <div key={i} className="url-item">{url}</div>
              ))}
            </div>
          )}
        </Section>

        {/* Recent Heartbeats */}
        {data.heartbeats?.length > 0 && (
          <Section title={`Recent Heartbeats (last ${data.heartbeats.length})`}>
            <div className="hb-table-wrapper">
              <table className="hb-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>URL</th>
                    <th>Mouse</th>
                    <th>Clicks</th>
                    <th>Keys</th>
                    <th>Scrolls</th>
                    <th>Copies</th>
                    <th>Navs</th>
                  </tr>
                </thead>
                <tbody>
                  {data.heartbeats.map((hb, i) => (
                    <tr key={i}>
                      <td className="mono">{new Date(hb.timestamp).toLocaleTimeString()}</td>
                      <td className="mono url-cell">{hb.url || "—"}</td>
                      <td>{hb.mouseMoves ?? "—"}</td>
                      <td>{hb.clicks ?? "—"}</td>
                      <td>{hb.keydowns ?? "—"}</td>
                      <td>{hb.scrolls ?? "—"}</td>
                      <td>{hb.copyPastes ?? "—"}</td>
                      <td>{hb.navigationEvents ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        )}

        {/* Raw JSON */}
        <RawJson data={data} />
      </div>
    </div>
  );
}

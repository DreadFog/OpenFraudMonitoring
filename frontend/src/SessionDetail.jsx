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
  const { deviceId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getSessionDetail(deviceId)
      .then(setData)
      .catch(() => setError("Failed to load session."));
  }, [deviceId]);

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
  const nav = fp.navigator || {};
  const scr = fp.screen || {};
  const tz  = fp.timezone || {};
  const bot = fp.botSignals || {};
  const gl  = fp.webgl || {};
  const apis = fp.apis || {};
  const net  = fp.network || {};
  const stor = fp.storage || {};
  const pubIP = fp.publicIP || {};

  const riskClass =
    data.risk_score >= 60 ? "risk-high" : data.risk_score >= 30 ? "risk-med" : "risk-low";

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
          <Field label="Device ID"    value={data.device_id} />
          <Field label="Client IP"    value={data.client_ip} />
          <Field label="Public IP"    value={pubIP.ip} />
          <Field label="Country"      value={pubIP.country} />
          <Field label="City"         value={pubIP.city} />
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

        {/* Navigator / Device */}
        <Section title="Browser & Device">
          <Field label="User Agent"           value={nav.userAgent} />
          <Field label="Platform"             value={nav.platform} />
          <Field label="Operating System"     value={fp.operatingSystem} />
          <Field label="Device Type"          value={nav.isWorkstation ? "Workstation" : nav.isMobile ? "Mobile" : "Unknown"} />
          <Field label="Language"             value={nav.language} />
          <Field label="Vendor"               value={nav.vendor} />
          <Field label="CPU Cores"            value={nav.hardwareConcurrency} />
          <Field label="Device Memory (GB)"   value={nav.deviceMemory} />
          <Field label="Cookies Enabled"      value={nav.cookieEnabled} />
          <Field label="Online"               value={nav.onLine} />
        </Section>

        {/* Screen */}
        <Section title="Screen">
          <Field label="Resolution"       value={scr.width && scr.height ? `${scr.width} × ${scr.height}` : null} />
          <Field label="Available"        value={scr.availWidth && scr.availHeight ? `${scr.availWidth} × ${scr.availHeight}` : null} />
          <Field label="Color Depth"      value={scr.colorDepth} />
          <Field label="Pixel Depth"      value={scr.pixelDepth} />
          <Field label="Device Pixel Ratio" value={scr.devicePixelRatio} />
          <Field label="Inner Window"     value={scr.innerWidth && scr.innerHeight ? `${scr.innerWidth} × ${scr.innerHeight}` : null} />
          <Field label="Outer Window"     value={scr.outerWidth && scr.outerHeight ? `${scr.outerWidth} × ${scr.outerHeight}` : null} />
        </Section>

        {/* Timezone */}
        <Section title="Timezone">
          <Field label="Timezone" value={tz.timezone} />
          <Field label="UTC Offset (min)" value={tz.offset} />
          <Field label="Locale"   value={tz.locale} />
        </Section>

        {/* WebGL */}
        <Section title="WebGL">
          <Field label="Vendor"           value={gl.vendor} />
          <Field label="Renderer"         value={gl.renderer} />
          <Field label="Masked Vendor"    value={gl.maskedVendor} />
          <Field label="Masked Renderer"  value={gl.maskedRenderer} />
          <Field label="GL Version"       value={gl.version} />
          <Field label="GLSL Version"     value={gl.shadingVersion} />
          <Field label="Extensions"       value={gl.extensions ? `${gl.extensions.length} supported` : null} />
        </Section>

        {/* Canvas & Audio */}
        <Section title="Canvas & Audio">
          <Field label="Canvas Available" value={fp.canvas ? "Yes" : "No"} />
          <Field label="Winding Rule"     value={fp.canvas?.windingSupport !== undefined ? String(fp.canvas.windingSupport) : null} />
          <Field label="Audio Fingerprint" value={fp.audio || "Unavailable"} />
        </Section>

        {/* Network */}
        {net && Object.keys(net).length > 0 && (
          <Section title="Network">
            <Field label="Effective Type" value={net.effectiveType} />
            <Field label="Downlink (Mbps)" value={net.downlink} />
            <Field label="RTT (ms)"       value={net.rtt} />
            <Field label="Save Data"      value={net.saveData} />
          </Section>
        )}

        {/* Storage */}
        <Section title="Storage">
          <Field label="localStorage"   value={stor.localStorage ? "Available" : "Blocked"} />
          <Field label="sessionStorage" value={stor.sessionStorage ? "Available" : "Blocked"} />
          <Field label="IndexedDB"      value={stor.indexedDB ? "Available" : "Blocked"} />
          <Field label="Cookies"        value={stor.cookieEnabled ? "Enabled" : "Disabled"} />
        </Section>

        {/* Browser APIs */}
        <Section title="Browser APIs">
          <Field label="Crypto"            value={apis.crypto ? "Yes" : "No"} />
          <Field label="Crypto Subtle"     value={apis.cryptoSubtle ? "Yes" : "No"} />
          <Field label="WebGL"             value={apis.webGL ? "Yes" : "No"} />
          <Field label="WebGL2"            value={apis.webGL2 ? "Yes" : "No"} />
          <Field label="WebRTC"            value={apis.webRTC ? "Yes" : "No"} />
          <Field label="Service Worker"    value={apis.serviceWorker ? "Yes" : "No"} />
          <Field label="Payment Request"   value={apis.paymentRequest ? "Yes" : "No"} />
          <Field label="MutationObserver"  value={apis.MutationObserver ? "Yes" : "No"} />
          <Field label="Performance API"   value={apis.performance ? "Yes" : "No"} />
        </Section>

        {/* Bot Signals */}
        <Section title="Bot Signals">
          <Field label="WebDriver"         value={bot.webdriver ? "DETECTED" : "No"} />
          <Field label="PhantomJS"         value={bot.phantom ? "DETECTED" : "No"} />
          <Field label="Nightmare"         value={bot.nightmare ? "DETECTED" : "No"} />
          <Field label="Puppeteer"         value={bot.puppeteer ? "DETECTED" : "No"} />
          <Field label="Selenium"          value={bot.selenium ? "DETECTED" : "No"} />
          <Field label="ChromeDriver Props" value={bot.cdcProps?.length > 0 ? bot.cdcProps.join(", ") : "None"} />
          <Field label="Empty Languages"   value={bot.languages_empty ? "Yes" : "No"} />
          <Field label="No Plugins"        value={bot.noPlugins ? "Yes" : "No"} />
          <Field label="Native Check"      value={bot.nativeCheckPassed === false ? "FAILED (spoofed)" : "Passed"} />
        </Section>

        {/* WebRTC IPs */}
        {fp.webrtcIPs?.length > 0 && (
          <Section title="WebRTC IPs">
            <div className="ip-list">
              {fp.webrtcIPs.map((ip, i) => (
                <span key={i} className="ip-item">{ip}</span>
              ))}
            </div>
          </Section>
        )}

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

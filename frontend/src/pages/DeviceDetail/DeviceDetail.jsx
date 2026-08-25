import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../../api";
import IpIntelPopover from "../../components/IpIntelPopover/IpIntelPopover";
import { buildGraphUrl, deviceSeed } from "../Graph/graphLink";
import "../Devices/Devices.css";

function Field({ label, value, popoverIp }) {
  if (value === null || value === undefined || value === "") return null;
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

function confidenceClass(confidence) {
  if (confidence >= 0.9) return "confidence-high";
  if (confidence >= 0.75) return "confidence-med";
  return "confidence-low";
}

function deviceTypeLabel(deviceType) {
  if (deviceType === "mobile") return "📱 Mobile";
  if (deviceType === "workstation") return "💻 Workstation";
  return "❓ Unknown";
}

export default function DeviceDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getDeviceDetail(id)
      .then(setData)
      .catch(() => setError("Failed to load device."));
  }, [id]);

  if (error) {
    return (
      <div className="sd-container">
        <p className="sd-error">{error}</p>
        <button className="back-btn" onClick={() => navigate("/devices")}>Back</button>
      </div>
    );
  }

  if (!data) {
    return <div className="sd-container"><p className="sd-loading">Loading…</p></div>;
  }

  return (
    <div className="sd-container">
      <header className="sd-header">
        <button className="back-btn" onClick={() => navigate("/devices")}>← Back</button>
        <h1>Device #{data.id}</h1>
        <span className={`confidence-badge ${confidenceClass(data.confidence)}`}>
          {Math.round((data.confidence || 0) * 100)}% match
        </span>
        <button className="graph-explore-btn" onClick={() => navigate(buildGraphUrl([deviceSeed(data.id)]))}>
          🕸 Explore in graph
        </button>
      </header>

      <div className="sd-body sd-body--split">
        <div className="sd-col-left">
          <Section title="Identity">
            <Field label="Client Device UUID" value={data.cookie_id} />
            <Field label="Device Type" value={deviceTypeLabel(data.device_type)} />
            <Field label="Match Confidence" value={`${Math.round((data.confidence || 0) * 100)}%`} />
            <Field label="First Seen" value={new Date(data.first_seen).toLocaleString()} />
            <Field label="Last Seen" value={new Date(data.last_seen).toLocaleString()} />
            <Field label="Recent IPs" value={(data.recent_ips || []).join(", ")} />
          </Section>

          <Section title="Hardware (Tier A)">
            <Field label="Platform" value={data.platform} />
            <Field label="Screen Resolution" value={data.screen_width && data.screen_height ? `${data.screen_width} × ${data.screen_height}` : null} />
            <Field label="Pixel Depth" value={data.pixel_depth} />
            <Field label="Color Depth" value={data.color_depth} />
            <Field label="Speakers" value={data.speakers} />
            <Field label="Microphones" value={data.microphones} />
            <Field label="Webcams" value={data.webcams} />
            <Field label="WebGL Vendor" value={data.webgl_vendor} />
            <Field label="WebGL Renderer" value={data.webgl_renderer} />
            <Field label="Architecture" value={data.hev_architecture} />
            <Field label="Bitness" value={data.hev_bitness} />
            <Field label="Model" value={data.hev_model} />
          </Section>

          <Section title="OS / Browser (Tier B)">
            <Field label="Reported Platform" value={data.hev_platform} />
            <Field label="Platform Version" value={data.hev_platform_version} />
            <Field label="Timezone" value={data.timezone} />
            <Field label="Language" value={data.language} />
          </Section>
        </div>

        <div className="sd-col-right">
          <Section title={`Linked Sessions (${data.sessions.length})`}>
            <table className="sessions-table">
              <thead>
                <tr>
                  <th>Fingerprint ID</th>
                  <th>IP</th>
                  <th>Risk Score</th>
                  <th>Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {data.sessions.map((s) => (
                  <tr key={s.fsid} onClick={() => navigate(`/session/${s.fsid}`)}>
                    <td className="device-id">{s.fsid.length > 32 ? `${s.fsid.slice(0, 32)}...` : s.fsid}</td>
                    <td>{s.client_ip} <IpIntelPopover ip={s.client_ip} /></td>
                    <td><span className={`risk-badge ${s.risk_score >= 60 ? "risk-high" : s.risk_score >= 30 ? "risk-med" : "risk-low"}`}>{s.risk_score}</span></td>
                    <td className="time-ago">{new Date(s.last_seen).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        </div>
      </div>
    </div>
  );
}

import React, { useEffect, useState } from "react";
import { api } from "../../api";
import "../CorsSettings/CorsSettings.css";

const KEY = "dashboard.default_time_range";

export default function DashboardGlobalSettings() {
  const [preset, setPreset] = useState("24h");
  const [saved, setSaved] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getGlobalSettings().then((settings) => {
      setPreset(settings[KEY] || "24h");
      setSaved(settings[KEY] || "24h");
    }).catch(() => setError("Failed to load dashboard settings"));
  }, []);

  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api.updateGlobalSettings({ [KEY]: preset });
      setSaved(preset);
    } catch (err) {
      setError(err.message || "Failed to save dashboard settings");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="cors-settings">
      <h3>Dashboard Settings</h3>
      <p className="cors-description">Default Last Seen range for dashboards without a user-selected range.</p>
      {error && <div className="cors-error">{error}</div>}
      <form className="cors-add-form" onSubmit={save}>
        <select className="dashboard-global-select" aria-label="Default Last Seen range" value={preset} onChange={(event) => setPreset(event.target.value)} disabled={saving}>
          <option value="24h">24 hours</option>
          <option value="7d">7 days</option>
          <option value="1m">1 month</option>
        </select>
        <button type="submit" disabled={saving || saved === preset}>{saving ? "Saving…" : "Save"}</button>
      </form>
    </div>
  );
}
import React, { useEffect, useState } from "react";
import { api } from "../../api";
import "../CorsSettings/CorsSettings.css";

const KEY = "dashboard.default_time_range";
const WIDTH_KEY = "layout.content_width_percent";

export default function DashboardGlobalSettings() {
  const [preset, setPreset] = useState("24h");
  const [saved, setSaved] = useState(null);
  const [width, setWidth] = useState(100);
  const [savedWidth, setSavedWidth] = useState(100);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getGlobalSettings().then((settings) => {
      setPreset(settings[KEY] || "24h");
      setSaved(settings[KEY] || "24h");
      setWidth(Number(settings[WIDTH_KEY]) || 100);
      setSavedWidth(Number(settings[WIDTH_KEY]) || 100);
    }).catch(() => setError("Failed to load dashboard settings"));
  }, []);

  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const nextWidth = Number(width);
      if (!Number.isInteger(nextWidth) || nextWidth < 25 || nextWidth > 100) {
        throw new Error("Content width must be an integer between 25% and 100%");
      }
      await api.updateGlobalSettings({ [KEY]: preset, [WIDTH_KEY]: nextWidth });
      setSaved(preset);
      setSavedWidth(nextWidth);
      window.dispatchEvent(new Event("ofm:global-settings-updated"));
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
        <label className="dashboard-width-field">Content width
          <input type="number" min="25" max="100" step="5" value={width} onChange={(event) => setWidth(event.target.value)} disabled={saving} /> %
        </label>
        <button type="submit" disabled={saving || (saved === preset && savedWidth === Number(width))}>{saving ? "Saving…" : "Save"}</button>
      </form>
    </div>
  );
}
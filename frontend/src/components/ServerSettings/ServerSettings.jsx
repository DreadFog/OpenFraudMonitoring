import React, { useEffect, useState } from "react";
import { api } from "../../api";
import "../CorsSettings/CorsSettings.css";
import "./ServerSettings.css";

const LOCATION_KEY = "server.location";
const TIMEZONE_KEY = "server.timezone";
const TIMEZONES = [...new Set(["UTC", ...(typeof Intl.supportedValuesOf === "function"
  ? Intl.supportedValuesOf("timeZone") : [])])].sort();

export default function ServerSettings() {
  const [form, setForm] = useState({ name: "", latitude: "", longitude: "", timezone: "UTC" });
  const [saved, setSaved] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    setError("");
    api.getGlobalSettings().then((settings) => {
      if (!active) return;
      const location = settings[LOCATION_KEY] || {};
      const values = {
        name: location.name || "",
        latitude: location.latitude == null ? "" : String(location.latitude),
        longitude: location.longitude == null ? "" : String(location.longitude),
        timezone: settings[TIMEZONE_KEY] || "UTC",
      };
      setForm(values);
      setSaved(values);
    }).catch((err) => {
      if (active) setError(err.message || "Failed to load server settings");
    });
    return () => { active = false; };
  }, [reload]);

  const update = (key, value) => {
    setForm({ ...form, [key]: value });
    setSuccess(false);
  };

  const save = async (event) => {
    event.preventDefault();
    const latitude = form.latitude.trim() === "" ? null : Number(form.latitude);
    const longitude = form.longitude.trim() === "" ? null : Number(form.longitude);
    if ((latitude === null) !== (longitude === null)) {
      setError("Provide both latitude and longitude, or leave both empty");
      return;
    }
    if (latitude !== null && (!Number.isFinite(latitude) || Math.abs(latitude) > 90 ||
        !Number.isFinite(longitude) || Math.abs(longitude) > 180)) {
      setError("Latitude must be between -90 and 90; longitude between -180 and 180");
      return;
    }
    const timezone = form.timezone.trim();
    if (!timezone) {
      setError("A server timezone is required");
      return;
    }
    setSaving(true);
    setError("");
    setSuccess(false);
    try {
      await api.updateGlobalSettings({
        [LOCATION_KEY]: { name: form.name.trim(), latitude, longitude },
        [TIMEZONE_KEY]: timezone,
      });
      const values = { ...form, name: form.name.trim(), timezone };
      setForm(values);
      setSaved(values);
      setSuccess(true);
    } catch (err) {
      setError(err.message || "Failed to save server settings");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="cors-settings">
      <h3>Server Location</h3>
      {error && <div className="cors-error" role="alert">{error}</div>}
      {error && saved === null && (
        <button type="button" className="logging-btn" onClick={() => setReload(reload + 1)}>Retry</button>
      )}
      <form className="server-settings-form" onSubmit={save}>
        <fieldset disabled={saved === null || saving} className="server-settings-fields">
          <label className="server-location-name">
            Location
            <input type="text" maxLength={200} value={form.name} onChange={(event) => update("name", event.target.value)} />
          </label>
          <label>
            Latitude
            <input type="number" step="any" min="-90" max="90" value={form.latitude} onChange={(event) => update("latitude", event.target.value)} />
          </label>
          <label>
            Longitude
            <input type="number" step="any" min="-180" max="180" value={form.longitude} onChange={(event) => update("longitude", event.target.value)} />
          </label>
          <label className="server-location-name">
            Timezone
            <input type="text" list="server-timezones" required maxLength={128} value={form.timezone} onChange={(event) => update("timezone", event.target.value)} />
            <datalist id="server-timezones">
              {TIMEZONES.map((timezone) => <option key={timezone} value={timezone} />)}
            </datalist>
          </label>
        </fieldset>
        <div className="cors-add-form">
          <button type="submit" disabled={saved === null || saving || JSON.stringify(form) === JSON.stringify(saved)}>
            {saving ? "Saving..." : "Save"}
          </button>
          {success && <span role="status" className="server-settings-status">Server settings saved</span>}
        </div>
      </form>
    </section>
  );
}
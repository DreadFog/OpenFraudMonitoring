import React, { useEffect, useState } from "react";
import { api } from "../../api";
import "../CorsSettings/CorsSettings.css";

const RETENTION_KEY = "data.retention_months";

export default function RetentionSettings() {
  const [months, setMonths] = useState("");
  const [saved, setSaved] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    api.getGlobalSettings()
      .then((settings) => {
        if (!active) return;
        const value = settings[RETENTION_KEY] ?? 6;
        setMonths(String(value));
        setSaved(value);
      })
      .catch((err) => {
        if (active) setError(err.message || "Failed to load retention settings");
      });
    return () => { active = false; };
  }, []);

  const save = async (event) => {
    event.preventDefault();
    const value = Number(months);
    if (!Number.isSafeInteger(value) || value < 1) {
      setError("Retention must be a positive whole number of months");
      return;
    }
    if (value < saved && !window.confirm(
      "Shortening retention permanently deletes older inactive data at the next cleanup. Continue?"
    )) return;
    setSaving(true);
    setError("");
    try {
      await api.updateGlobalSettings({ [RETENTION_KEY]: value });
      setSaved(value);
    } catch (err) {
      setError(err.message || "Failed to save retention settings");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="cors-settings">
      <h3>Data Retention</h3>
      {error && <div className="cors-error" role="alert">{error}</div>}
      <form className="cors-add-form" onSubmit={save} style={{ flexWrap: "wrap" }}>
        <label htmlFor="retention-months" style={{ alignSelf: "center", color: "var(--text)" }}>
          Inactivity period (months)
        </label>
        <input
          id="retention-months"
          type="number"
          min="1"
          step="1"
          required
          value={months}
          onChange={(event) => setMonths(event.target.value)}
          disabled={saved === null || saving}
          style={{ minWidth: 80, width: 120, flex: "1 1 120px" }}
        />
        <button type="submit" disabled={saved === null || saving || Number(months) === saved}>
          {saving ? "Saving..." : "Save"}
        </button>
      </form>
      {saved !== null && (
        <p className="cors-description" role="status">
          Current policy: {saved} {saved === 1 ? "month" : "months"} of inactivity
        </p>
      )}
      <p className="cors-description">
        Deletion is permanent. Policy changes apply at the next hourly cleanup.
      </p>
    </section>
  );
}
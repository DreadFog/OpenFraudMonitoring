import React, { useEffect, useState } from "react";
import { api } from "../../api";
import "../CorsSettings/CorsSettings.css";

const THRESHOLD_KEY = "graph.expand_warn_threshold";

export default function GraphGlobalSettings() {
  const [threshold, setThreshold] = useState("");
  const [saved, setSaved] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getGlobalSettings()
      .then((s) => {
        const v = s[THRESHOLD_KEY];
        setThreshold(String(v ?? 1000));
        setSaved(v ?? 1000);
      })
      .catch(() => setError("Failed to load global settings"));
  }, []);

  const save = async (e) => {
    e.preventDefault();
    const n = parseInt(threshold, 10);
    if (!Number.isFinite(n) || n < 1) {
      setError("Threshold must be a positive integer");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await api.updateGlobalSettings({ [THRESHOLD_KEY]: n });
      setSaved(n);
    } catch (e) {
      setError(e.message || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="cors-settings">
      <h3>Graph Settings</h3>
      <p className="cors-description">
        Expansions in the graph view that would add this many nodes or more prompt a
        confirmation warning before running.
      </p>

      {error && <div className="cors-error">{error}</div>}

      <form className="cors-add-form" onSubmit={save}>
        <input
          type="number"
          min="1"
          placeholder="1000"
          value={threshold}
          onChange={(e) => setThreshold(e.target.value)}
          disabled={saving}
        />
        <button type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
      </form>

      {saved != null && (
        <p className="cors-description">Current threshold: {saved} nodes</p>
      )}
    </div>
  );
}

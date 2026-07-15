import React, { useEffect, useState } from "react";
import { api } from "../../api";
import "../CorsSettings/CorsSettings.css";

const CENSOR_KEY = "clipboard_censor";

export default function PrivacySettings() {
  const [censor, setCensor] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getGlobalSettings()
      .then((s) => {
        setCensor(s[CENSOR_KEY] !== false);
        setLoaded(true);
      })
      .catch(() => setError("Failed to load global settings"));
  }, []);

  const toggle = async (value) => {
    setCensor(value);
    setSaving(true);
    setError("");
    try {
      await api.updateGlobalSettings({ [CENSOR_KEY]: value });
    } catch (e) {
      setError(e.message || "Failed to save");
      setCensor(!value);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="cors-settings">
      <h3>Privacy</h3>
      <p className="cors-description">
        Censor captured clipboard contents (copy/paste) in the session view, showing
        only the first and last character.
      </p>
      {error && <div className="cors-error">{error}</div>}
      <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14, color: "#c9d1d9" }}>
        <input
          type="checkbox"
          checked={censor}
          disabled={!loaded || saving}
          onChange={(e) => toggle(e.target.checked)}
        />
        Censor clipboard contents
      </label>
    </div>
  );
}

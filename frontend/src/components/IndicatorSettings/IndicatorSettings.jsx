import React, { useEffect, useState } from "react";
import { api } from "../../api";
import "../CorsSettings/CorsSettings.css";

const KEY = "intel.indicator_automation";

export default function IndicatorSettings() {
  const [policy, setPolicy] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let active = true;
    api.getGlobalSettings()
      .then((settings) => { if (active) setPolicy(settings[KEY]); })
      .catch((err) => { if (active) setError(err.message || "Failed to load indicator policy"); });
    return () => { active = false; };
  }, []);

  function update(key, value) {
    setPolicy((previous) => ({ ...previous, [key]: value }));
    setSaved(false);
  }

  async function save(event) {
    event.preventDefault();
    const next = {
      ...policy,
      risk_threshold: Number(policy.risk_threshold),
      lookback_minutes: Number(policy.lookback_minutes),
      validity_hours: Number(policy.validity_hours),
    };
    for (const [key, minimum, maximum] of [
      ["risk_threshold", 0, 100], ["lookback_minutes", 1, 10080], ["validity_hours", 1, 8760],
    ]) {
      if (!Number.isSafeInteger(next[key]) || String(policy[key]).trim() === "" || next[key] < minimum || next[key] > maximum) {
        setError(`${key} must be a whole number between ${minimum} and ${maximum}`);
        return;
      }
    }
    setSaving(true);
    setError("");
    try {
      await api.updateGlobalSettings({ [KEY]: next });
      setPolicy(next);
      setSaved(true);
    } catch (err) {
      setError(err.message || "Failed to save indicator policy");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="cors-settings">
      <h3>IP Indicator Automation</h3>
      {error && <div className="cors-error" role="alert">{error}</div>}
      {policy && (
        <form className="cors-add-form" onSubmit={save} style={{ flexWrap: "wrap" }}>
          <label>
            <input type="checkbox" checked={policy.enabled} disabled={saving}
              onChange={(event) => update("enabled", event.target.checked)} />
            {" "}Enable automatic IPv4/IPv6 indicators
          </label>
          {[
            ["risk_threshold", "Minimum risk score (inclusive)", 0, 100],
            ["lookback_minutes", "Recent activity window (minutes)", 1, 10080],
            ["validity_hours", "Validity after activity (hours)", 1, 8760],
          ].map(([key, label, min, max]) => (
            <label key={key}>
              {label}
              <input type="number" min={min} max={max} step="1" required disabled={saving}
                value={policy[key]} onChange={(event) => update(key, event.target.value)} />
            </label>
          ))}
          <button type="submit" disabled={saving}>{saving ? "Saving..." : "Save"}</button>
        </form>
      )}
      {saved && <p className="cors-description" role="status">Indicator policy saved.</p>}
      <p className="cors-description">
        Runs after periodic rules. Qualifying activity renews all based-on indicators,
        including imported and revoked indicators, or creates one if none exist.
        With 24-hour validity, an IP seen at 19:00 stays valid until at least 19:00
        tomorrow. Repeated scans of unchanged activity do not add extra days.
        Manual creation uses the same validity duration, even when automation is disabled.
      </p>
    </section>
  );
}

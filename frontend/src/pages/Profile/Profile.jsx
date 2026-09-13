import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "../../AuthContext";
import { api } from "../../api";
import { useUserSettings } from "../../hooks/useUserSettings";
import "./Profile.css";

function DashboardPreferencesSection() {
  const { settings, loading, update } = useUserSettings();
  const [dashboards, setDashboards] = useState([]);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    api.getDashboards().then(setDashboards).catch(console.error);
  }, []);

  const currentDefault = settings?.defaultDashboardId ?? null;

  const handleChange = async (e) => {
    const val = e.target.value;
    const newId = val === "" ? null : Number(val);
    setSaving(true);
    setMessage(null);
    try {
      await update({ defaultDashboardId: newId });
      setMessage("Default dashboard updated.");
      setTimeout(() => setMessage(null), 2500);
    } catch {
      setMessage("Failed to update default dashboard.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="profile-section">
      <h3>Preferences</h3>
      <div className="preference-row">
        <label htmlFor="default-dashboard-select" className="preference-label">
          Default Dashboard:
        </label>
        <select
          id="default-dashboard-select"
          className="preference-select"
          value={currentDefault ?? ""}
          disabled={loading || saving}
          onChange={handleChange}
        >
          <option value="">Default System Dashboard</option>
          {dashboards.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        {message && <span className="preference-msg">{message}</span>}
      </div>
    </div>
  );
}

function TokenSection() {
  const [tokens, setTokens] = useState([]);
  const [newTokenName, setNewTokenName] = useState("");
  const [createdToken, setCreatedToken] = useState(null);
  const [copied, setCopied] = useState(false);

  const loadTokens = useCallback(async () => {
    try {
      const data = await api.getTokens();
      setTokens(data);
    } catch {}
  }, []);

  useEffect(() => { loadTokens(); }, [loadTokens]);

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      const data = await api.createToken(newTokenName || "default");
      setCreatedToken(data.token);
      setNewTokenName("");
      loadTokens();
    } catch {}
  };

  const handleRevoke = async (id) => {
    if (!window.confirm("Revoke this token?")) return;
    try {
      await api.revokeToken(id);
      loadTokens();
    } catch {}
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(createdToken);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="profile-section">
      <h3>My API Tokens</h3>

      {createdToken && (
        <div className="token-reveal">
          <p>New token created. Copy it now — it won't be shown again:</p>
          <code>{createdToken}</code>
          <button onClick={handleCopy}>{copied ? "Copied!" : "Copy"}</button>
          <button onClick={() => setCreatedToken(null)}>Dismiss</button>
        </div>
      )}

      <form className="token-create-form" onSubmit={handleCreate}>
        <input
          placeholder="Token name"
          value={newTokenName}
          onChange={(e) => setNewTokenName(e.target.value)}
        />
        <button type="submit">Create Token</button>
      </form>

      <table className="profile-table">
        <thead>
          <tr>
            <th>Prefix</th>
            <th>Name</th>
            <th>Created</th>
            <th>Last Used</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {tokens.map((t) => (
            <tr key={t.id}>
              <td><code>{t.token_prefix}...</code></td>
              <td>{t.name}</td>
              <td>{t.created_at ? new Date(t.created_at).toLocaleDateString() : "-"}</td>
              <td>{t.last_used_at ? new Date(t.last_used_at).toLocaleString() : "Never"}</td>
              <td>
                <button className="btn-danger-sm" onClick={() => handleRevoke(t.id)}>Revoke</button>
              </td>
            </tr>
          ))}
          {tokens.length === 0 && (
            <tr><td colSpan="5" className="profile-empty">No API tokens</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default function Profile() {
  const { user } = useAuth();

  return (
    <div className="profile-page">
      <header className="profile-header">
        <h1>Profile</h1>
        <p className="profile-sub">Signed in as <strong>{user?.username}</strong> ({user?.role})</p>
      </header>
      <DashboardPreferencesSection />
      <TokenSection />
    </div>
  );
}

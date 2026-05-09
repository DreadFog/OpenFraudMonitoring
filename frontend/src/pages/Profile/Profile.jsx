import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "../../AuthContext";
import { api } from "../../api";
import "./Profile.css";

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
      <TokenSection />
    </div>
  );
}

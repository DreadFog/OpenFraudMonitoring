import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "../../AuthContext";
import { api } from "../../api";
import CorsSettings from "../../components/CorsSettings/CorsSettings";
import "./Users.css";

function CreateUserForm({ onCreated }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await api.createUser(username, role === "connector" ? "" : password, role);
      setUsername("");
      setPassword("");
      setRole("user");
      onCreated();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <form className="users-create-form" onSubmit={handleSubmit}>
      <h3>Create User</h3>
      {error && <div className="users-error">{error}</div>}
      <input
        placeholder="Username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        required
      />
      {role !== "connector" && (
        <input
          placeholder="Password (min 8 chars)"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      )}
      <select value={role} onChange={(e) => setRole(e.target.value)}>
        <option value="user">User</option>
        <option value="admin">Admin</option>
        <option value="connector">Connector</option>
      </select>
      <button type="submit">Create</button>
    </form>
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
    <div className="users-section">
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

      <table className="users-table">
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
            <tr><td colSpan="5" className="users-empty">No API tokens</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default function Users() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const isAdmin = user?.role === "admin";

  const loadUsers = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const data = await api.getUsers();
      setUsers(data);
    } catch {}
  }, [isAdmin]);

  useEffect(() => { loadUsers(); }, [loadUsers]);

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this user and all their tokens?")) return;
    try {
      await api.deleteUser(id);
      loadUsers();
    } catch {}
  };

  const handleToggleActive = async (u) => {
    try {
      await api.updateUser(u.id, { is_active: !u.is_active });
      loadUsers();
    } catch {}
  };

  return (
    <div className="users-page">
      <TokenSection />

      {isAdmin && (
        <div className="users-section">
          <h2>User Management</h2>
          <CreateUserForm onCreated={loadUsers} />

          <table className="users-table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Role</th>
                <th>Active</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className={!u.is_active ? "row-inactive" : ""}>
                  <td>{u.username}</td>
                  <td><span className={`role-badge role-${u.role}`}>{u.role}</span></td>
                  <td>
                    <button className="btn-toggle" onClick={() => handleToggleActive(u)}>
                      {u.is_active ? "Active" : "Inactive"}
                    </button>
                  </td>
                  <td>{u.created_at ? new Date(u.created_at).toLocaleDateString() : "-"}</td>
                  <td>
                    {u.id !== user.id && (
                      <button className="btn-danger-sm" onClick={() => handleDelete(u.id)}>Delete</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {isAdmin && <CorsSettings />}
    </div>
  );
}

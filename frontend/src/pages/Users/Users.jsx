import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "../../AuthContext";
import { api } from "../../api";
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

export default function UserManagement() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);

  const loadUsers = useCallback(async () => {
    try {
      const data = await api.getUsers();
      setUsers(data);
    } catch {}
  }, []);

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
  );
}

import React, { useState, useEffect, useCallback } from "react";
import { api } from "../../api";
import "./CorsSettings.css";

export default function CorsSettings() {
  const [origins, setOrigins] = useState([]);
  const [newOrigin, setNewOrigin] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const loadOrigins = useCallback(async () => {
    try {
      const data = await api.getCorsOrigins();
      setOrigins(data);
    } catch (err) {
      setError(`Failed to load CORS origins: ${err.message}`);
    }
  }, []);

  useEffect(() => {
    loadOrigins();
  }, [loadOrigins]);

  const handleAddOrigin = async (e) => {
    e.preventDefault();
    setError("");
    const origin = newOrigin.trim();

    if (!origin) {
      setError("Origin URL required");
      return;
    }

    if (!origin.startsWith("http://") && !origin.startsWith("https://")) {
      setError("Origin must start with http:// or https://");
      return;
    }

    setLoading(true);
    try {
      await api.addCorsOrigin(origin);
      setNewOrigin("");
      loadOrigins();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleOrigin = async (originId) => {
    try {
      await api.toggleCorsOrigin(originId);
      loadOrigins();
    } catch (err) {
      setError(`Failed to toggle origin: ${err.message}`);
    }
  };

  const handleDeleteOrigin = async (originId) => {
    if (!window.confirm("Delete this CORS origin?")) return;
    try {
      await api.deleteCorsOrigin(originId);
      loadOrigins();
    } catch (err) {
      setError(`Failed to delete origin: ${err.message}`);
    }
  };

  return (
    <div className="cors-settings">
      <h3>CORS Allowed Origins</h3>
      <p className="cors-description">
        Configure which domains are allowed to embed the fingerprint script.
      </p>

      {error && <div className="cors-error">{error}</div>}

      <form className="cors-add-form" onSubmit={handleAddOrigin}>
        <input
          type="url"
          placeholder="https://example.com"
          value={newOrigin}
          onChange={(e) => setNewOrigin(e.target.value)}
          disabled={loading}
        />
        <button type="submit" disabled={loading}>
          {loading ? "Adding..." : "Add Origin"}
        </button>
      </form>

      <table className="cors-table">
        <thead>
          <tr>
            <th>Origin</th>
            <th>Status</th>
            <th>Added</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {origins.length === 0 ? (
            <tr>
              <td colSpan="4" className="cors-empty">
                No CORS origins configured
              </td>
            </tr>
          ) : (
            origins.map((o) => (
              <tr key={o.id} className={!o.active ? "cors-row-inactive" : ""}>
                <td>
                  <code>{o.origin}</code>
                </td>
                <td>
                  <button
                    className={`cors-status-badge ${
                      o.active ? "cors-active" : "cors-inactive"
                    }`}
                    onClick={() => handleToggleOrigin(o.id)}
                  >
                    {o.active ? "Active" : "Inactive"}
                  </button>
                </td>
                <td>{o.created_at ? new Date(o.created_at).toLocaleDateString() : "-"}</td>
                <td>
                  <button
                    className="cors-btn-delete"
                    onClick={() => handleDeleteOrigin(o.id)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

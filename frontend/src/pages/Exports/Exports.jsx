import React, { useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import { useAuth } from "../../AuthContext";
import "./Exports.css";

const TYPE_OPTIONS = [
  "ipv4-addr",
  "ipv6-addr",
  "user-agent",
  "autonomous-system",
  "location",
  "indicator",
  "malware",
  "campaign",
  "intrusion-set",
  "relationship",
];

const EMPTY_FORM = {
  name: "",
  description: "",
  is_active: true,
  entity_type: "ipv4-addr",
  filter_logic: "AND",
  filter_drafts: [{ field: "", op: "", value: "" }],
};

function fmtDate(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

export default function ExportsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [feeds, setFeeds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [filterSchema, setFilterSchema] = useState([]);

  const sortedFeeds = useMemo(
    () => [...feeds].sort((a, b) => new Date(b.updated_at || 0) - new Date(a.updated_at || 0)),
    [feeds],
  );

  async function loadFeeds() {
    setLoading(true);
    setError("");
    try {
      const res = await api.listTaxiiFeeds(true);
      setFeeds(Array.isArray(res.feeds) ? res.feeds : []);
    } catch (e) {
      setError(e.message || "Failed to load feeds");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadFeeds();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const entityType = form.entity_type;
    if (!entityType) {
      setFilterSchema([]);
      return;
    }

    api.getIntelFilterSchema(entityType)
      .then((res) => setFilterSchema(Array.isArray(res.fields) ? res.fields : []))
      .catch(() => setFilterSchema([]));
  }, [form.entity_type]);

  function resetForm() {
    setEditingId(null);
    setForm(EMPTY_FORM);
  }

  function toggleType(type) {
    setForm((prev) => ({ ...prev, entity_type: type }));
  }

  function schemaFieldByName(name) {
    return filterSchema.find((f) => f.name === name);
  }

  function addFilterDraft() {
    setForm((prev) => ({
      ...prev,
      filter_drafts: [...prev.filter_drafts, { field: "", op: "", value: "" }],
    }));
  }

  function removeFilterDraft(idx) {
    setForm((prev) => {
      const next = prev.filter_drafts.filter((_, i) => i !== idx);
      return {
        ...prev,
        filter_drafts: next.length ? next : [{ field: "", op: "", value: "" }],
      };
    });
  }

  function updateFilterDraft(idx, patch) {
    setForm((prev) => ({
      ...prev,
      filter_drafts: prev.filter_drafts.map((row, i) => (i === idx ? { ...row, ...patch } : row)),
    }));
  }

  function buildFiltersPayload() {
    const filters = [];
    for (const row of form.filter_drafts) {
      if (!row.field || !row.op) continue;
      const meta = schemaFieldByName(row.field);
      if (!meta) continue;
      const rawValue = row.value;
      if (meta.type !== "boolean" && String(rawValue || "").trim() === "") continue;
      filters.push({
        field: row.field,
        op: row.op,
        value: meta.type === "boolean" ? String(rawValue || "false") : String(rawValue),
      });
    }
    return filters;
  }

  async function submit(e) {
    e.preventDefault();
    if (!isAdmin) return;

    setSaving(true);
    setError("");
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description.trim(),
        is_active: !!form.is_active,
        object_types: [form.entity_type],
        filters: buildFiltersPayload(),
      };

      if (!payload.name) {
        throw new Error("Name is required");
      }
      if (!form.entity_type) {
        throw new Error("Select an entity type");
      }

      if (editingId) {
        await api.updateTaxiiFeed(editingId, payload);
      } else {
        await api.createTaxiiFeed(payload);
      }
      await loadFeeds();
      resetForm();
    } catch (e2) {
      setError(e2.message || "Failed to save feed");
    } finally {
      setSaving(false);
    }
  }

  function startEdit(feed) {
    setEditingId(feed.id);
    setForm({
      name: feed.name || "",
      description: feed.description || "",
      is_active: !!feed.is_active,
      entity_type: (Array.isArray(feed.object_types) && feed.object_types[0]) ? feed.object_types[0] : "ipv4-addr",
      filter_logic: "AND",
      filter_drafts: Array.isArray(feed.filters) && feed.filters.length > 0
        ? feed.filters.map((f) => ({
            field: String(f.field || ""),
            op: String(f.op || ""),
            value: String(f.value ?? ""),
          }))
        : [{ field: "", op: "", value: "" }],
    });
  }

  async function removeFeed(feed) {
    if (!isAdmin) return;
    if (!window.confirm(`Delete TAXII feed \"${feed.name}\"?`)) return;

    setSaving(true);
    setError("");
    try {
      await api.deleteTaxiiFeed(feed.id);
      await loadFeeds();
      if (editingId === feed.id) resetForm();
    } catch (e) {
      setError(e.message || "Failed to delete feed");
    } finally {
      setSaving(false);
    }
  }

  function browseFeed(feed) {
    const token = localStorage.getItem("ofm_token") || "";
    const sep = feed.objects_url.includes("?") ? "&" : "?";
    const url = `${feed.objects_url}${sep}access_token=${encodeURIComponent(token)}`;
    window.open(url, "_blank", "noopener,noreferrer");
  }

  return (
    <div className="exports-page">
      <header className="exports-header">
        <h1>TAXII Exports</h1>
        <p>Manage authenticated TAXII collections and copy feed object URLs for downstream ingesters.</p>
      </header>

      {error && <div className="exports-error">{error}</div>}

      {isAdmin && (
        <section className="exports-card">
          <h2>{editingId ? `Edit Feed #${editingId}` : "Create Feed"}</h2>
          <form className="exports-form" onSubmit={submit}>
            <label>
              Name
              <input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="Fraud Intel Export"
                required
              />
            </label>

            <label>
              Description
              <input
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                placeholder="Optional description"
              />
            </label>

            {editingId && (
              <label className="exports-inline-check">
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
                />
                Active
              </label>
            )}

            <label>
              Entity type
              <select
                value={form.entity_type}
                onChange={(e) => toggleType(e.target.value)}
              >
                {TYPE_OPTIONS.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>

            <div className="exports-types">
              <span>Filters for {form.entity_type}</span>
              <div className="exports-filter-logic">
                <label>
                  Logic
                  <select
                    value={form.filter_logic}
                    onChange={(e) => setForm((f) => ({ ...f, filter_logic: e.target.value }))}
                  >
                    <option value="AND">Match all (AND)</option>
                    <option value="OR">Match any (OR)</option>
                  </select>
                </label>
              </div>
              <div className="exports-filter-list">
                {form.filter_drafts.map((row, idx) => {
                  const meta = schemaFieldByName(row.field);
                  const operators = meta?.operators || [];
                  const isBoolean = meta?.type === "boolean";
                  return (
                    <div key={idx} className="exports-filter-row">
                      <select
                        value={row.field}
                        onChange={(e) => updateFilterDraft(idx, { field: e.target.value, op: "", value: "" })}
                      >
                        <option value="">Field...</option>
                        {filterSchema.map((f) => (
                          <option key={f.name} value={f.name}>{f.label}</option>
                        ))}
                      </select>

                      <select
                        value={row.op}
                        onChange={(e) => updateFilterDraft(idx, { op: e.target.value })}
                        disabled={!row.field}
                      >
                        <option value="">Operator...</option>
                        {operators.map((op) => (
                          <option key={op} value={op}>{op}</option>
                        ))}
                      </select>

                      {isBoolean ? (
                        <select
                          value={row.value || "false"}
                          onChange={(e) => updateFilterDraft(idx, { value: e.target.value })}
                          disabled={!row.op}
                        >
                          <option value="true">true</option>
                          <option value="false">false</option>
                        </select>
                      ) : (
                        <input
                          type="text"
                          value={row.value}
                          onChange={(e) => updateFilterDraft(idx, { value: e.target.value })}
                          placeholder={meta ? `Value (${meta.type})` : "Value..."}
                          disabled={!row.op}
                        />
                      )}

                      <button
                        className="exports-btn exports-btn-secondary exports-btn-small"
                        type="button"
                        onClick={() => removeFilterDraft(idx)}
                      >
                        Remove
                      </button>
                    </div>
                  );
                })}
              </div>
              <div className="exports-filter-actions">
                <button className="exports-btn exports-btn-secondary exports-btn-small" type="button" onClick={addFilterDraft}>
                  + Add filter
                </button>
              </div>
            </div>

            <div className="exports-actions">
              <button className="exports-btn" type="submit" disabled={saving}>
                {editingId ? "Save Feed" : "Create Feed"}
              </button>
              <button className="exports-btn exports-btn-secondary" type="button" onClick={resetForm} disabled={saving}>
                Clear
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="exports-card">
        <div className="exports-list-head">
          <h2>TAXII Feeds</h2>
          <button className="exports-btn exports-btn-secondary" type="button" onClick={loadFeeds} disabled={loading || saving}>
            Refresh
          </button>
        </div>

        {loading ? (
          <p className="exports-muted">Loading feeds...</p>
        ) : sortedFeeds.length === 0 ? (
          <p className="exports-muted">No TAXII feeds configured for this view.</p>
        ) : (
          <div className="exports-table-wrap">
            <table className="exports-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Type</th>
                  <th>Filters</th>
                  <th>Browse</th>
                  <th>Updated</th>
                  {isAdmin && <th>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {sortedFeeds.map((feed) => (
                  <tr key={feed.id}>
                    <td>
                      <div className="exports-name">{feed.name}</div>
                      {feed.description && <div className="exports-sub">{feed.description}</div>}
                    </td>
                    <td>{feed.is_active ? "active" : "inactive"}</td>
                    <td>{(feed.object_types || ["-"])[0]}</td>
                    <td>{Array.isArray(feed.filters) ? feed.filters.length : 0}</td>
                    <td>
                      <button className="exports-btn exports-btn-small" type="button" onClick={() => browseFeed(feed)}>
                        Browse
                      </button>
                    </td>
                    <td>{fmtDate(feed.updated_at)}</td>
                    {isAdmin && (
                      <td>
                        <div className="exports-row-actions">
                          <button className="exports-btn exports-btn-small" type="button" onClick={() => startEdit(feed)}>
                            Edit
                          </button>
                          <button className="exports-btn exports-btn-danger exports-btn-small" type="button" onClick={() => removeFeed(feed)}>
                            Delete
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

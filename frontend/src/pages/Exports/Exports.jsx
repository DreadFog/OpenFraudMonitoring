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
  export_format: "taxii",
  is_public: false,
  include_headers: true,
  csv_delimiter: ",",
  auto_update: false,
  update_interval_minutes: 60,
  export_fields: ["value"],
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
  const [exportFields, setExportFields] = useState([]);

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

  useEffect(() => {
    let active = true;
    api.getExportFields(form.entity_type)
      .then((res) => {
        if (!active) return;
        setExportFields(res.fields || []);
        setForm((prev) => {
          const fields = prev.export_fields.filter((field) => !field || res.fields.includes(field));
          return { ...prev, export_fields: fields.length ? fields : [res.fields.includes('value') ? 'value' : 'id'] };
        });
      })
      .catch((err) => { if (active) setError(err.message || "Failed to load export fields"); });
    return () => { active = false; };
  }, [form.entity_type]);

  function resetForm() {
    setEditingId(null);
    setForm(EMPTY_FORM);
  }

  function toggleType(type) {
    setForm((prev) => ({ ...prev, entity_type: type, export_fields: [type === 'relationship' ? 'id' : 'value'], filter_drafts: [{ field: "", op: "", value: "" }] }));
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
        filter_logic: form.filter_logic,
        export_format: form.export_format,
        is_public: form.is_public,
        include_headers: form.include_headers,
        csv_delimiter: form.csv_delimiter,
        auto_update: form.export_format === 'csv' && form.auto_update,
        update_interval_minutes: Number(form.update_interval_minutes),
        export_fields: form.export_format === 'csv' ? form.export_fields : [],
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
      export_format: feed.export_format || "taxii",
      is_public: !!feed.is_public,
      include_headers: feed.include_headers !== false,
      csv_delimiter: feed.csv_delimiter || ",",
      auto_update: !!feed.auto_update,
      update_interval_minutes: feed.update_interval_minutes || 60,
      export_fields: feed.export_fields?.length ? feed.export_fields : ["value"],
      entity_type: (Array.isArray(feed.object_types) && feed.object_types[0]) ? feed.object_types[0] : "ipv4-addr",
      filter_logic: feed.filter_logic || "AND",
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
    if (!window.confirm(`Delete feed \"${feed.name}\"?`)) return;

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
    const url = feed.is_public ? feed.objects_url : `${feed.objects_url}${sep}access_token=${encodeURIComponent(token)}`;
    window.open(url, "_blank", "noopener,noreferrer");
  }

  return (
    <div className="exports-page">
      <header className="page-header exports-header">
        <h1>Exports</h1>
      </header>

      {error && <div className="exports-error">{error}</div>}

      {isAdmin && (
        <section className="exports-card">
          <h2>{editingId ? `Edit Feed #${editingId}` : "Create Feed"}</h2>
          <form className="exports-form" onSubmit={submit}>
            <label>
              Format
              <select value={form.export_format} onChange={(event) => setForm((prev) => ({ ...prev, export_format: event.target.value }))}>
                <option value="taxii">TAXII 2.1</option>
                <option value="csv">CSV</option>
              </select>
            </label>
            <label className="exports-inline-check">
              <input type="checkbox" checked={form.is_public} onChange={(event) => setForm((prev) => ({ ...prev, is_public: event.target.checked }))} />
              Public (no authentication)
            </label>
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
              {form.export_format === 'csv' && (
                <div className="exports-csv-options">
                  <label>
                    Delimiter
                    <select value={form.csv_delimiter} onChange={(event) => setForm((prev) => ({ ...prev, csv_delimiter: event.target.value }))}>
                      <option value=",">Comma (,)</option>
                      <option value=";">Semicolon (;)</option>
                      <option value={"\t"}>Tab</option>
                      <option value="|">Pipe (|)</option>
                    </select>
                  </label>
                  <label className="exports-inline-check">
                    <input type="checkbox" checked={form.include_headers} onChange={(event) => setForm((prev) => ({ ...prev, include_headers: event.target.checked }))} />
                    Include headers
                  </label>
                  <label className="exports-inline-check">
                    <input type="checkbox" checked={form.auto_update} onChange={(event) => setForm((prev) => ({ ...prev, auto_update: event.target.checked }))} />
                    Auto-update (incremental)
                  </label>
                  {form.auto_update && <label>
                    Update interval (minutes)
                    <input type="number" min="1" max="525600" step="1" required value={form.update_interval_minutes} onChange={(event) => setForm((prev) => ({ ...prev, update_interval_minutes: event.target.value }))} />
                  </label>}
                  <fieldset className="exports-fields">
                    <legend>Export columns</legend>
                    <div className="exports-column-list">
                      {form.export_fields.map((field, index) => (
                        <div key={index} className="exports-column-row">
                          <label>
                            Column {String.fromCharCode(65 + index)}
                            <select
                              required
                              value={field}
                              onChange={(event) => setForm((prev) => ({
                                ...prev,
                                export_fields: prev.export_fields.map((value, position) => position === index ? event.target.value : value),
                              }))}
                            >
                              <option value="">Select field...</option>
                              {exportFields.map((option) => (
                                <option key={option} value={option} disabled={option !== field && form.export_fields.includes(option)}>{option}</option>
                              ))}
                            </select>
                          </label>
                          <button
                            className="exports-btn exports-btn-secondary"
                            type="button"
                            title={`Remove column ${String.fromCharCode(65 + index)}`}
                            aria-label={`Remove column ${String.fromCharCode(65 + index)}`}
                            disabled={form.export_fields.length === 1}
                            onClick={() => setForm((prev) => ({ ...prev, export_fields: prev.export_fields.filter((value, position) => position !== index) }))}
                          >×</button>
                        </div>
                      ))}
                    </div>
                    <button
                      className="exports-btn exports-btn-secondary exports-btn-small"
                      type="button"
                      disabled={form.export_fields.length >= 26 || form.export_fields.length >= exportFields.length || form.export_fields.includes('')}
                      onClick={() => setForm((prev) => ({ ...prev, export_fields: [...prev.export_fields, ''] }))}
                    >+ Add column</button>
                  </fieldset>
                </div>
              )}
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
          <h2>Feeds</h2>
          <button className="exports-btn exports-btn-secondary" type="button" onClick={loadFeeds} disabled={loading || saving}>
            Refresh
          </button>
        </div>

        {loading ? (
          <p className="exports-muted">Loading feeds...</p>
        ) : sortedFeeds.length === 0 ? (
          <p className="exports-muted">No feeds configured.</p>
        ) : (
          <div className="exports-table-wrap">
            <table className="exports-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Format</th>
                  <th>Access</th>
                  <th>Updates</th>
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
                    <td>{(feed.export_format || 'taxii').toUpperCase()}</td>
                    <td>{feed.is_public ? 'public' : 'private'}</td>
                    <td>{feed.export_format === 'csv' ? (feed.auto_update ? `Every ${feed.update_interval_minutes} min` : 'Full export') : 'Live collection'}
                      {feed.last_generated_at && <div className="exports-sub">{fmtDate(feed.last_generated_at)}</div>}
                    </td>
                    <td>{(feed.object_types || ["-"])[0]}</td>
                    <td>{Array.isArray(feed.filters) ? feed.filters.length : 0}</td>
                    <td>
                      <button className="exports-btn exports-btn-small" type="button" onClick={() => browseFeed(feed)}>
                        {feed.export_format === 'csv' ? 'Download' : 'Browse'}
                      </button>
                      <div className="exports-feed-url"><a href={feed.objects_url} target="_blank" rel="noreferrer">{feed.objects_url}</a></div>
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

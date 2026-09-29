import React, { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import { useAuth } from "../../AuthContext";
import FilterBuilder from "../../components/FilterBuilder/FilterBuilder";
import "./Rules.css";

const EMPTY_FORM = {
  name: "",
  description: "",
  enabled: true,
  rule_type: "realtime",
  logic: "AND",
  score_modifier: 0,
  period_seconds: 0,
  conditions: [],
  sequences: [],
};

const newStep = () => ({ event_type: "", filters: [] });
const newSequence = () => ({ steps: [newStep(), newStep()] });

function isIncomplete(f) {
  return !f.field || !f.op;
}

function pickRulePayload(form) {
  if (form.conditions.some(isIncomplete)) {
    throw new Error("Complete or remove every condition (field and operator are required).");
  }
  if (form.sequences.length > 0) {
    if (form.rule_type !== "periodic") throw new Error("Sequences are only allowed in periodic rules.");
    if (form.logic !== "AND") throw new Error("Rules with sequences must use AND logic.");
    for (const seq of form.sequences) {
      if (seq.steps.some((s) => !s.event_type)) throw new Error("Every sequence step needs an event type.");
      if (seq.steps.some((s) => s.filters.some(isIncomplete))) {
        throw new Error("Complete or remove every sequence step condition.");
      }
    }
  }

  return {
    name: form.name.trim() || "Untitled Rule",
    description: form.description,
    enabled: !!form.enabled,
    rule_type: form.rule_type,
    logic: form.logic,
    score_modifier: Number(form.score_modifier) || 0,
    period_seconds: Number(form.period_seconds) || 0,
    conditions: [
      ...form.conditions,
      ...form.sequences.map((seq) => ({ type: "sequence", steps: seq.steps })),
    ],
  };
}

function SequenceEditor({ index, sequence, eventSchema, onChange, onRemove }) {
  const eventTypes = Object.keys(eventSchema);
  const updateStep = (i, patch) =>
    onChange({ steps: sequence.steps.map((s, j) => (j === i ? { ...s, ...patch } : s)) });
  const removeStep = (i) => onChange({ steps: sequence.steps.filter((_, j) => j !== i) });

  return (
    <div className="rules-sequence">
      <div className="rules-sequence-head">
        <span className="rules-sequence-title">Sequence {index + 1}</span>
        <span className="rules-muted">Steps must occur in this order within the session.</span>
        <button type="button" className="filter-clear-btn" onClick={onRemove}>Remove sequence</button>
      </div>
      {sequence.steps.map((step, i) => (
        <div className="rules-step" key={i}>
          <div className="rules-step-head">
            <span className="rules-step-num">{i + 1}</span>
            <select
              className="filter-select"
              value={step.event_type}
              onChange={(e) => updateStep(i, { event_type: e.target.value, filters: [] })}
            >
              <option value="">Event type…</option>
              {eventTypes.map((t) => (
                <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
              ))}
            </select>
            <button
              type="button"
              className="filter-remove"
              onClick={() => removeStep(i)}
              disabled={sequence.steps.length <= 2}
              title={sequence.steps.length <= 2 ? "A sequence needs at least 2 steps" : "Remove step"}
            >
              ×
            </button>
          </div>
          {step.event_type && (
            <FilterBuilder
              className="rules-filter-builder"
              title="Where"
              addLabel="+ Add Condition"
              schema={eventSchema[step.event_type] || []}
              filters={step.filters}
              onChange={(filters) => updateStep(i, { filters })}
              onClear={() => updateStep(i, { filters: [] })}
              suggest={null}
            />
          )}
        </div>
      ))}
      <button
        type="button"
        className="filter-add-btn"
        onClick={() => onChange({ steps: [...sequence.steps, newStep()] })}
      >
        + Add Step
      </button>
    </div>
  );
}

export default function RulesPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [replaceOnImport, setReplaceOnImport] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [schema, setSchema] = useState([]);
  const [eventSchema, setEventSchema] = useState({});
  const fileInputRef = useRef(null);

  const sortedRules = useMemo(
    () => [...rules].sort((a, b) => new Date(b.updated_at || 0) - new Date(a.updated_at || 0)),
    [rules]
  );

  async function loadRules() {
    setLoading(true);
    setError("");
    try {
      const data = await api.getRules();
      setRules(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(e.message || "Failed to fetch rules");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRules();
    api.getSchema().then(setSchema).catch(() => setSchema([]));
    api.getSequenceSchema().then(setEventSchema).catch(() => setEventSchema({}));
  }, []);

  function resetForm() {
    setEditingId(null);
    setForm(EMPTY_FORM);
  }

  function onEdit(rule) {
    const conditions = rule.conditions || [];
    setEditingId(rule.id);
    setForm({
      name: rule.name || "",
      description: rule.description || "",
      enabled: !!rule.enabled,
      rule_type: rule.rule_type || "realtime",
      logic: rule.logic || "AND",
      score_modifier: rule.score_modifier ?? 0,
      period_seconds: rule.period_seconds ?? 0,
      conditions: conditions
        .filter((c) => c.type !== "sequence")
        .map((c) => ({ field: c.field || "", op: c.op || "", value: c.value == null ? "" : String(c.value) })),
      sequences: conditions
        .filter((c) => c.type === "sequence")
        .map((c) => ({
          steps: (c.steps || []).map((s) => ({ event_type: s.event_type || "", filters: s.filters || [] })),
        })),
    });
  }

  async function onSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const payload = pickRulePayload(form);
      if (editingId) {
        await api.updateRule(editingId, payload);
      } else {
        await api.createRule(payload);
      }
      await loadRules();
      resetForm();
    } catch (err) {
      setError(err.message || "Failed to save rule");
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(ruleId) {
    if (!window.confirm("Delete this rule?")) return;
    setError("");
    try {
      await api.deleteRule(ruleId);
      setRules((prev) => prev.filter((r) => r.id !== ruleId));
      if (editingId === ruleId) resetForm();
    } catch (e) {
      setError(e.message || "Failed to delete rule");
    }
  }

  async function onToggle(rule) {
    setError("");
    try {
      const updated = await api.updateRule(rule.id, { enabled: !rule.enabled });
      setRules((prev) => prev.map((r) => (r.id === rule.id ? updated : r)));
      if (editingId === rule.id) {
        setForm((f) => ({ ...f, enabled: updated.enabled }));
      }
    } catch (e) {
      setError(e.message || "Failed to toggle rule");
    }
  }

  function onExport() {
    const payload = sortedRules.map((r) => ({
      name: r.name,
      description: r.description,
      enabled: !!r.enabled,
      rule_type: r.rule_type,
      logic: r.logic,
      conditions: r.conditions || [],
      score_modifier: r.score_modifier || 0,
      period_seconds: r.period_seconds || 0,
    }));

    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    a.href = url;
    a.download = `ofm-rules-${stamp}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function onImportFile(file) {
    const text = await file.text();
    let incoming;
    try {
      incoming = JSON.parse(text);
    } catch {
      throw new Error("Invalid JSON file.");
    }
    if (!Array.isArray(incoming)) {
      throw new Error("Import file must be a JSON array of rules.");
    }

    const sanitized = incoming.map((raw, idx) => {
      if (!raw || typeof raw !== "object") {
        throw new Error(`Rule at index ${idx} is not an object.`);
      }
      const conditions = Array.isArray(raw.conditions) ? raw.conditions : [];
      return {
        name: String(raw.name || `Imported Rule ${idx + 1}`),
        description: String(raw.description || ""),
        enabled: raw.enabled !== false,
        rule_type: raw.rule_type === "periodic" ? "periodic" : "realtime",
        logic: raw.logic === "OR" ? "OR" : "AND",
        conditions,
        score_modifier: Number(raw.score_modifier) || 0,
        period_seconds: Number(raw.period_seconds) || 0,
      };
    });

    if (replaceOnImport && rules.length > 0) {
      for (const r of rules) {
        await api.deleteRule(r.id);
      }
    }

    for (const r of sanitized) {
      await api.createRule(r);
    }
  }

  async function onImportChange(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;

    setSaving(true);
    setError("");
    try {
      await onImportFile(file);
      await loadRules();
    } catch (err) {
      setError(err.message || "Import failed");
    } finally {
      setSaving(false);
    }
  }

  if (!isAdmin) {
    return <div className="rules-page"><p className="rules-error">Admin access required.</p></div>;
  }

  return (
    <div className="rules-page">
      <header className="page-header rules-header">
        <h1>Rules</h1>
        <p>Manage detection rules, toggle activation, and import/export JSON rule sets.</p>
        <div className="rules-actions">
          <button className="rules-btn" type="button" onClick={loadRules} disabled={loading || saving}>Refresh</button>
          <button className="rules-btn" type="button" onClick={onExport} disabled={loading || saving}>Export JSON</button>
          <button className="rules-btn" type="button" onClick={() => fileInputRef.current?.click()} disabled={saving}>Import JSON</button>
          <label className="rules-check">
            <input
              type="checkbox"
              checked={replaceOnImport}
              onChange={(e) => setReplaceOnImport(e.target.checked)}
            />
            Replace existing rules
          </label>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            onChange={onImportChange}
            style={{ display: "none" }}
          />
        </div>
      </header>

      {error && <div className="rules-error">{error}</div>}

      <section className="rules-card">
        <h2>{editingId ? `Edit Rule #${editingId}` : "Create Rule"}</h2>
        <form className="rules-form" onSubmit={onSubmit}>
          <label>
            Name
            <input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} required />
          </label>
          <label>
            Description
            <input value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
          </label>
          <label>
            Rule Type
            <select value={form.rule_type} onChange={(e) => setForm((f) => ({ ...f, rule_type: e.target.value }))}>
              <option value="realtime">realtime</option>
              <option value="periodic">periodic</option>
            </select>
          </label>
          <label>
            Logic
            <select value={form.logic} onChange={(e) => setForm((f) => ({ ...f, logic: e.target.value }))}>
              <option value="AND">AND — all conditions must match</option>
              <option value="OR" disabled={form.sequences.length > 0}>OR — any condition matches</option>
            </select>
          </label>
          <label>
            Score Modifier
            <input
              type="number"
              value={form.score_modifier}
              onChange={(e) => setForm((f) => ({ ...f, score_modifier: e.target.value }))}
            />
          </label>
          <label>
            Period Seconds
            <input
              type="number"
              value={form.period_seconds}
              onChange={(e) => setForm((f) => ({ ...f, period_seconds: e.target.value }))}
              disabled={form.rule_type !== "periodic"}
            />
          </label>
          <label className="rules-inline-check">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
            />
            Enabled
          </label>
          <div className="rules-wide rules-builder">
            <FilterBuilder
              className="rules-filter-builder"
              title={`Conditions (${form.logic === "AND" ? "all must match" : "any matches"})`}
              addLabel="+ Add Condition"
              schema={schema}
              filters={form.conditions}
              onChange={(conditions) => setForm((f) => ({ ...f, conditions }))}
              onClear={() => setForm((f) => ({ ...f, conditions: [] }))}
            />

            <div className="rules-sequences">
              <div className="filter-header">
                <span className="filter-title">Event sequences</span>
                <button
                  type="button"
                  className="filter-add-btn"
                  onClick={() => setForm((f) => ({ ...f, logic: "AND", sequences: [...f.sequences, newSequence()] }))}
                  disabled={form.rule_type !== "periodic"}
                >
                  + Add Sequence
                </button>
                {form.rule_type !== "periodic" && (
                  <span className="rules-muted">Available for periodic rules only.</span>
                )}
              </div>
              {form.sequences.map((seq, i) => (
                <SequenceEditor
                  key={i}
                  index={i}
                  sequence={seq}
                  eventSchema={eventSchema}
                  onChange={(next) => setForm((f) => ({ ...f, sequences: f.sequences.map((s, j) => (j === i ? next : s)) }))}
                  onRemove={() => setForm((f) => ({ ...f, sequences: f.sequences.filter((_, j) => j !== i) }))}
                />
              ))}
            </div>
          </div>
          <div className="rules-form-actions rules-wide">
            <button className="rules-btn" type="submit" disabled={saving}>{editingId ? "Save" : "Create"}</button>
            <button className="rules-btn rules-btn-secondary" type="button" onClick={resetForm} disabled={saving}>Clear</button>
          </div>
        </form>
      </section>

      <section className="rules-card">
        <h2>Current Rules ({sortedRules.length})</h2>
        {loading ? (
          <p>Loading...</p>
        ) : sortedRules.length === 0 ? (
          <p className="rules-muted">No rules yet.</p>
        ) : (
          <div className="rules-table-wrap">
            <table className="rules-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Logic</th>
                  <th>Enabled</th>
                  <th>Score</th>
                  <th>Conditions</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {sortedRules.map((r) => (
                  <tr key={r.id}>
                    <td>{r.id}</td>
                    <td>
                      <div className="rules-name">{r.name}</div>
                      {r.description && <div className="rules-sub">{r.description}</div>}
                    </td>
                    <td>{r.rule_type}</td>
                    <td>{r.logic}</td>
                    <td>
                      <button
                        className={`rules-toggle ${r.enabled ? "rules-on" : "rules-off"}`}
                        type="button"
                        onClick={() => onToggle(r)}
                      >
                        {r.enabled ? "Active" : "Inactive"}
                      </button>
                    </td>
                    <td>{r.score_modifier}</td>
                    <td>{Array.isArray(r.conditions) ? r.conditions.length : 0}</td>
                    <td>
                      <div className="rules-row-actions">
                        <button className="rules-btn rules-btn-small" type="button" onClick={() => onEdit(r)}>Edit</button>
                        <button className="rules-btn rules-btn-danger rules-btn-small" type="button" onClick={() => onDelete(r.id)}>Delete</button>
                      </div>
                    </td>
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

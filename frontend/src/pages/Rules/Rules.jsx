import React, { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import { useAuth } from "../../AuthContext";
import "./Rules.css";

const EMPTY_FORM = {
  name: "",
  description: "",
  enabled: true,
  rule_type: "realtime",
  logic: "AND",
  score_modifier: 0,
  period_seconds: 0,
  conditionsText: "[]",
};

function pickRulePayload(form) {
  let parsed = [];
  try {
    parsed = JSON.parse(form.conditionsText || "[]");
  } catch {
    throw new Error("Conditions must be valid JSON.");
  }
  if (!Array.isArray(parsed)) {
    throw new Error("Conditions JSON must be an array.");
  }

  return {
    name: form.name.trim() || "Untitled Rule",
    description: form.description,
    enabled: !!form.enabled,
    rule_type: form.rule_type,
    logic: form.logic,
    score_modifier: Number(form.score_modifier) || 0,
    period_seconds: Number(form.period_seconds) || 0,
    conditions: parsed,
  };
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
  }, []);

  function resetForm() {
    setEditingId(null);
    setForm(EMPTY_FORM);
  }

  function onEdit(rule) {
    setEditingId(rule.id);
    setForm({
      name: rule.name || "",
      description: rule.description || "",
      enabled: !!rule.enabled,
      rule_type: rule.rule_type || "realtime",
      logic: rule.logic || "AND",
      score_modifier: rule.score_modifier ?? 0,
      period_seconds: rule.period_seconds ?? 0,
      conditionsText: JSON.stringify(rule.conditions || [], null, 2),
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
      <header className="rules-header">
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
              <option value="AND">AND</option>
              <option value="OR">OR</option>
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
          <label className="rules-wide">
            Conditions JSON (array)
            <textarea
              rows={8}
              value={form.conditionsText}
              onChange={(e) => setForm((f) => ({ ...f, conditionsText: e.target.value }))}
            />
          </label>
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

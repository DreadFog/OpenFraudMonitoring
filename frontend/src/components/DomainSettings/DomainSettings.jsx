import React, { useEffect, useState } from "react";
import { api } from "../../api";
import "./DomainSettings.css";

const EMPTY = {
  domain: "",
  auth_cookie_name: "",
  form_action: "",
  form_method: "post",
  form_field_names: "",
  active: true,
};

function toForm(config) {
  return {
    ...config,
    form_field_names: (config.form_field_names || []).join(", "),
  };
}

export default function DomainSettings() {
  const [domains, setDomains] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [importFile, setImportFile] = useState(null);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      setDomains(await api.getDomainConfigs());
      setError("");
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => { load(); }, []);

  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    const payload = {
      ...form,
      form_field_names: form.form_field_names.split(",").map((name) => name.trim()).filter(Boolean),
    };
    try {
      if (editingId) await api.updateDomainConfig(editingId, payload);
      else await api.createDomainConfig(payload);
      setForm(EMPTY);
      setEditingId(null);
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  const edit = (config) => {
    setEditingId(config.id);
    setForm(toForm(config));
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this monitored domain configuration?")) return;
    try {
      await api.deleteDomainConfig(id);
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  const exportConfig = async () => {
    try {
      const payload = await api.exportDomainConfigs();
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "ofm-domains.json";
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message);
    }
  };

  const importConfig = async () => {
    if (!importFile) return;
    try {
      const text = await importFile.text();
      await api.importDomainConfigs(JSON.parse(text));
      setImportFile(null);
      document.getElementById("domain-config-file").value = "";
      await load();
    } catch (err) {
      setError(err.message || "Invalid JSON");
    }
  };

  return (
    <section className="logging-card">
      <h2>Monitored domains</h2>
      <p className="logging-muted">Configure authentication cookies and login-form patterns for each monitored host.</p>
      {error && <div className="logging-error">{error}</div>}
      <form onSubmit={submit} className="domain-form">
        <label>Domain<input required placeholder="example.com" value={form.domain} onChange={(e) => update("domain", e.target.value)} /></label>
        <label>Authentication cookie<input placeholder="Cookie name" value={form.auth_cookie_name} onChange={(e) => update("auth_cookie_name", e.target.value)} /></label>
        <label>Login form action<input placeholder="/login" value={form.form_action} onChange={(e) => update("form_action", e.target.value)} /></label>
        <label>Method<select value={form.form_method} onChange={(e) => update("form_method", e.target.value)}>
          <option value="post">POST</option>
          <option value="get">GET</option>
          <option value="put">PUT</option>
          <option value="patch">PATCH</option>
          <option value="delete">DELETE</option>
        </select></label>
        <label className="domain-form-wide">Login field names<input placeholder="email, password" value={form.form_field_names} onChange={(e) => update("form_field_names", e.target.value)} /></label>
        <label className="domain-checkbox"><input type="checkbox" checked={form.active} onChange={(e) => update("active", e.target.checked)} /> Active</label>
        <div className="domain-form-actions">
          <button className="domain-btn domain-btn-primary" type="submit">{editingId ? "Update domain" : "Add domain"}</button>
          {editingId && <button className="domain-btn domain-btn-secondary" type="button" onClick={() => { setEditingId(null); setForm(EMPTY); }}>Cancel</button>}
        </div>
      </form>
      <table className="logging-table">
        <thead><tr><th>Domain</th><th>Auth cookie</th><th>Form pattern</th><th>Status</th><th /></tr></thead>
        <tbody>
          {domains.map((config) => (
            <tr key={config.id}>
              <td><code>{config.domain}</code></td>
              <td>{config.auth_cookie_name || "-"}</td>
              <td>{config.form_action ? `${config.form_method.toUpperCase()} ${config.form_action}` : "-"}</td>
              <td>{config.active ? "Active" : "Inactive"}</td>
              <td className="domain-row-actions"><button className="domain-btn domain-btn-secondary" type="button" onClick={() => edit(config)}>Edit</button> <button className="domain-btn domain-btn-danger" type="button" onClick={() => remove(config.id)}>Delete</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="domain-transfer">
        <button className="domain-btn domain-btn-secondary" type="button" onClick={exportConfig}>Export JSON</button>
        <label className="domain-file-picker" htmlFor="domain-config-file">
          <span>{importFile ? importFile.name : "Choose JSON file"}</span>
          <input id="domain-config-file" type="file" accept=".json,application/json" onChange={(e) => setImportFile(e.target.files?.[0] || null)} />
        </label>
        <button className="domain-btn domain-btn-primary" type="button" onClick={importConfig} disabled={!importFile}>Import selected file</button>
      </div>
    </section>
  );
}

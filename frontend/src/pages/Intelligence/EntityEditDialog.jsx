import React, { useEffect, useRef, useState } from "react";

const FIXED_FIELDS = new Set(["type", "spec_version", "created", "modified"]);
const VALUE_FIELDS = {
  "ipv4-addr": ["value"],
  "ipv6-addr": ["value"],
  "user-agent": ["value"],
  "autonomous-system": ["number"],
  location: ["country", "x_opencti_aliases"],
};
const DATE_FIELDS = new Set(["created", "modified", "valid_from", "valid_until", "first_seen", "last_seen", "start_time", "stop_time"]);
const NUMBER_FIELDS = new Set(["number", "confidence", "x_opencti_score", "latitude", "longitude", "precision"]);

function labelFor(name) {
  return name.replace(/^x_opencti_/, "").replaceAll("_", " ").replace(/^\w/, (letter) => letter.toUpperCase());
}

function EntityField({ name, value, onChange, disabled }) {
  const label = labelFor(name);
  if (Array.isArray(value)) {
    return (
      <fieldset className="intel-edit-group" disabled={disabled}>
        <legend>{label}</legend>
        {value.map((item, index) => (
          <div className="intel-edit-array-item" key={index}>
            <EntityField name={`${label} ${index + 1}`} value={item} disabled={disabled}
              onChange={(next) => onChange(value.map((entry, i) => i === index ? next : entry))} />
            {!disabled && <button className="intel-btn" type="button"
              onClick={() => onChange(value.filter((_, i) => i !== index))}>Remove</button>}
          </div>
        ))}
        {!disabled && <button className="intel-btn" type="button" onClick={() => {
          const sample = value[0];
          const empty = sample && typeof sample === "object" && !Array.isArray(sample)
            ? Object.fromEntries(Object.entries(sample).map(([key, entry]) => [
              key, Array.isArray(entry) ? [] : typeof entry === "boolean" ? false : typeof entry === "number" ? 0 : "",
            ]))
            : "";
          onChange([...value, empty]);
        }}>Add item</button>}
      </fieldset>
    );
  }
  if (value !== null && typeof value === "object") {
    return (
      <fieldset className="intel-edit-group" disabled={disabled}>
        <legend>{label}</legend>
        {Object.entries(value).map(([key, entry]) => (
          <EntityField key={key} name={key} value={entry} disabled={disabled}
            onChange={(next) => onChange({ ...value, [key]: next })} />
        ))}
      </fieldset>
    );
  }
  if (typeof value === "boolean") {
    return (
      <label className="intel-edit-field intel-edit-checkbox">
        <input type="checkbox" checked={value} disabled={disabled}
          onChange={(event) => onChange(event.target.checked)} />
        {label}
      </label>
    );
  }
  const isNumber = typeof value === "number" || NUMBER_FIELDS.has(name);
  const isDate = DATE_FIELDS.has(name);
  const parsedDate = isDate && value ? new Date(value) : null;
  const dateValue = parsedDate && !Number.isNaN(parsedDate.getTime()) ? parsedDate.toISOString().slice(0, -1) : "";
  const multiline = name === "description" || name === "pattern";
  const Input = multiline ? "textarea" : "input";
  return (
    <label className="intel-edit-field">
      <span>{label}{isDate ? " (UTC)" : ""}{disabled ? " (read-only)" : ""}</span>
      <Input {...(!multiline ? { type: isDate ? "datetime-local" : isNumber ? "number" : "text", ...(isNumber ? { step: "any" } : isDate ? { step: "0.001" } : {}) } : { rows: 3 })}
        value={isDate ? dateValue : value ?? ""} disabled={disabled}
        onChange={(event) => {
          const next = event.target.value;
          onChange(isDate ? (next ? `${next}Z` : "") : isNumber ? (next === "" ? "" : Number(next)) : next);
        }} />
      {(name === "valid_from" || name === "valid_until") && (
        <small>Time is in UTC.{name === "valid_until" ? " Leave empty for no explicit expiry." : ""}</small>
      )}
    </label>
  );
}

export default function EntityEditDialog({ entity, saving, error, onSave, onClose }) {
  const dialog = useRef(null);
  const [draft, setDraft] = useState(() => {
    const raw = entity.stix_object || {};
    return entity.stix_type === "indicator"
      ? { name: "", description: "", valid_until: "", ...raw, revoked: Boolean(entity.platform?.revoked_explicitly) }
      : { ...raw };
  });
  useEffect(() => {
    const element = dialog.current;
    element.showModal();
    return () => element.close();
  }, []);
  return (
    <dialog ref={dialog} className="intel-edit-dialog" aria-labelledby="intel-edit-title"
      onCancel={(event) => { event.preventDefault(); if (!saving) onClose(); }}>
      <form onSubmit={(event) => {
        event.preventDefault();
        const payload = { ...draft };
        if (payload.valid_until === "") delete payload.valid_until;
        onSave(payload);
      }}>
        <h2 id="intel-edit-title">Edit entity</h2>
        <p className="intel-muted">Update the fields below. Read-only properties are managed by OFM.</p>
        <fieldset className="intel-edit-fields" disabled={saving}>
          {Object.entries(draft).filter(([key]) => key !== "id" && key !== "x_opencti_id").map(([key, value]) => (
            <EntityField key={key} name={key} value={value}
              disabled={saving || FIXED_FIELDS.has(key) || (VALUE_FIELDS[entity.stix_type] || []).includes(key)}
              onChange={(next) => setDraft((previous) => ({ ...previous, [key]: next }))} />
          ))}
        </fieldset>
        {error && <div className="intel-edit-error" role="alert">{error}</div>}
        <div className="intel-edit-actions">
          <button className="intel-btn intel-btn-primary" type="submit" disabled={saving}>
            {saving ? "Saving..." : "Save"}
          </button>
          <button className="intel-btn" type="button" disabled={saving} onClick={onClose}>Cancel</button>
        </div>
      </form>
    </dialog>
  );
}

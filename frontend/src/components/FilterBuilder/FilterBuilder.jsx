import React, { useState, useEffect, useRef } from "react";
import { api } from "../../api";
import "./FilterBuilder.css";

const OP_LABELS = {
  eq: "=",
  neq: "≠",
  contains: "contains",
  not_contains: "not contains",
  starts_with: "starts with",
  ends_with: "ends with",
  gt: ">",
  gte: "≥",
  lt: "<",
  lte: "≤",
};

/* ── Searchable field selector ── */
function FieldCombobox({ schema, value, onChange }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const wrapperRef = useRef(null);
  const inputRef = useRef(null);

  const filtered = schema.filter((f) =>
    f.label.toLowerCase().includes(search.toLowerCase())
  );

  const selectedLabel = schema.find((f) => f.name === value)?.label || "";

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleOpen = () => {
    setOpen(true);
    setSearch("");
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const handleSelect = (name) => {
    onChange(name);
    setOpen(false);
    setSearch("");
  };

  return (
    <div className="field-combobox" ref={wrapperRef}>
      <button
        type="button"
        className="filter-select field-combobox-trigger"
        onClick={handleOpen}
      >
        {selectedLabel || "Field…"}
      </button>
      {open && (
        <div className="field-combobox-dropdown">
          <input
            ref={inputRef}
            className="field-combobox-search"
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search fields…"
          />
          <div className="field-combobox-list">
            {filtered.length === 0 && (
              <div className="field-combobox-empty">No matches</div>
            )}
            {filtered.map((f) => (
              <div
                key={f.name}
                className={`field-combobox-item ${f.name === value ? "field-combobox-item-selected" : ""}`}
                onMouseDown={() => handleSelect(f.name)}
              >
                {f.label}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FilterRow({ filter, schema, onUpdate, onRemove }) {
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [valueFocused, setValueFocused] = useState(false);

  const fieldDef = schema.find((f) => f.name === filter.field);
  const operators = fieldDef ? fieldDef.operators : [];
  const isBoolean = fieldDef && fieldDef.type === "boolean";
  const isDate = fieldDef && fieldDef.type === "date";

  // Auto-set operator to "eq" for boolean fields
  useEffect(() => {
    if (isBoolean && filter.op !== "eq") {
      onUpdate("op", "eq");
    }
  }, [isBoolean, filter.op]);

  // Debounced suggestion fetch — triggers on focus or value change
  useEffect(() => {
    if (!filter.field || !valueFocused) {
      setSuggestions([]);
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const results = await api.getSuggestions(filter.field, filter.value || "");
        setSuggestions(results);
        setShowSuggestions(true);
      } catch {
        setSuggestions([]);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [filter.field, filter.value, valueFocused]);

  return (
    <div className="filter-row">
      <FieldCombobox
        schema={schema}
        value={filter.field}
        onChange={(v) => onUpdate("field", v)}
      />

      {!isBoolean && (
        <select
          className="filter-select filter-op"
          value={filter.op}
          onChange={(e) => onUpdate("op", e.target.value)}
          disabled={!filter.field}
        >
          <option value="">Op…</option>
          {operators.map((op) => (
            <option key={op.name} value={op.name}>
              {OP_LABELS[op.name] || op.label}
            </option>
          ))}
        </select>
      )}

      {isBoolean ? (
        <select
          className="filter-select"
          value={filter.value}
          onChange={(e) => onUpdate("value", e.target.value)}
        >
          <option value="">Value…</option>
          <option value="true">True</option>
          <option value="false">False</option>
        </select>
      ) : isDate ? (
        <div className="filter-date-wrapper">
          <input
            className="filter-input filter-date"
            type="date"
            value={filter.value ? new Date(Number(filter.value)).toISOString().slice(0, 10) : ""}
            onChange={(e) => {
              if (!e.target.value) { onUpdate("value", ""); return; }
              const prev = filter.value ? new Date(Number(filter.value)) : new Date();
              const [y, m, d] = e.target.value.split("-").map(Number);
              prev.setFullYear(y, m - 1, d);
              onUpdate("value", String(prev.getTime()));
            }}
            disabled={!filter.op}
          />
          <input
            className="filter-input filter-time"
            type="time"
            value={filter.value ? new Date(Number(filter.value)).toISOString().slice(11, 16) : ""}
            onChange={(e) => {
              if (!e.target.value) return;
              const prev = filter.value ? new Date(Number(filter.value)) : new Date();
              const [h, min] = e.target.value.split(":").map(Number);
              prev.setUTCHours(h, min, 0, 0);
              onUpdate("value", String(prev.getTime()));
            }}
            disabled={!filter.op || !filter.value}
          />
        </div>
      ) : (
      <div className="filter-value-wrapper">
        <input
          className="filter-input"
          type="text"
          value={filter.value}
          onChange={(e) => onUpdate("value", e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              setShowSuggestions(false);
              setValueFocused(false);
            }
          }}
          placeholder="Value…"
          disabled={!filter.op}
          onFocus={() => setValueFocused(true)}
          onBlur={() => setTimeout(() => { setShowSuggestions(false); setValueFocused(false); }, 200)}
        />
        {showSuggestions && suggestions.length > 0 && (
          <div className="suggestions-dropdown">
            {suggestions.map((s, i) => (
              <div
                key={i}
                className="suggestion-item"
                onMouseDown={() => {
                  onUpdate("value", String(s));
                  setShowSuggestions(false);
                }}
              >
                {String(s)}
              </div>
            ))}
          </div>
        )}
      </div>
      )}

      <button className="filter-remove" onClick={onRemove} title="Remove filter">
        ×
      </button>
    </div>
  );
}

export default function FilterBuilder({ schema, filters, onChange, onClear }) {
  const addFilter = () => {
    onChange([...filters, { field: "", op: "", value: "" }]);
  };

  const updateFilter = (index, key, value) => {
    const updated = [...filters];
    updated[index] = { ...updated[index], [key]: value };
    // Reset downstream selections when the field changes
    if (key === "field") {
      updated[index].op = "";
      updated[index].value = "";
    }
    onChange(updated);
  };

  const removeFilter = (index) => {
    onChange(filters.filter((_, i) => i !== index));
  };

  return (
    <div className="filter-builder">
      <div className="filter-header">
        <span className="filter-title">Filters</span>
        <button className="filter-add-btn" onClick={addFilter}>
          + Add Filter
        </button>
        {filters.length > 0 && (
            <button className="filter-clear-btn" onClick={onClear}>
              Clear
            </button>
        )}
      </div>
      {filters.map((filter, i) => (
        <FilterRow
          key={i}
          filter={filter}
          schema={schema}
          onUpdate={(key, value) => updateFilter(i, key, value)}
          onRemove={() => removeFilter(i)}
        />
      ))}
    </div>
  );
}

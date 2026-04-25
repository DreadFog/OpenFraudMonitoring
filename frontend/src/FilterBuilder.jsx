import React, { useState, useEffect } from "react";
import { api } from "./api";
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

function FilterRow({ filter, schema, onUpdate, onRemove }) {
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);

  const fieldDef = schema.find((f) => f.name === filter.field);
  const operators = fieldDef ? fieldDef.operators : [];
  const isBoolean = fieldDef && fieldDef.type === "boolean";

  // Auto-set operator to "eq" for boolean fields
  useEffect(() => {
    if (isBoolean && filter.op !== "eq") {
      onUpdate("op", "eq");
    }
  }, [isBoolean, filter.op]);

  // Debounced suggestion fetch
  useEffect(() => {
    if (!filter.field || !filter.value) {
      setSuggestions([]);
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const results = await api.getSuggestions(filter.field, filter.value);
        setSuggestions(results);
      } catch {
        setSuggestions([]);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [filter.field, filter.value]);

  return (
    <div className="filter-row">
      <select
        className="filter-select"
        value={filter.field}
        onChange={(e) => onUpdate("field", e.target.value)}
      >
        <option value="">Field…</option>
        {schema.map((f) => (
          <option key={f.name} value={f.name}>
            {f.label}
          </option>
        ))}
      </select>

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
            }
          }}
          placeholder="Value…"
          disabled={!filter.op}
          onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
          onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
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

export default function FilterBuilder({ schema, filters, onChange, onApply, onClear }) {
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
          <>
            <button className="filter-apply-btn" onClick={onApply}>
              Apply
            </button>
            <button className="filter-clear-btn" onClick={onClear}>
              Clear
            </button>
          </>
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

import React, { useState } from "react";
import FilterBuilder from "../FilterBuilder/FilterBuilder";
import "./WidgetWizard.css";

const WIDGET_TYPES = [
  { value: "stat", label: "Statistic", icon: "#️⃣", desc: "A single number — count of matching sessions" },
  { value: "pie", label: "Pie Chart", icon: "🥧", desc: "Distribution of values as proportional slices" },
  { value: "histogram", label: "Histogram", icon: "📊", desc: "Horizontal bar chart of value counts" },
  { value: "weighted_list", label: "Weighted List", icon: "📋", desc: "Ranked list with proportional bars" },
];

export default function WidgetWizard({ schema, onClose, onCreate, initialWidget }) {
  const isEditing = !!initialWidget;
  const [step, setStep] = useState(isEditing ? 3 : 1);
  const [type, setType] = useState(initialWidget?.type || "");
  const [field, setField] = useState(initialWidget?.field || "");
  const [filters, setFilters] = useState(initialWidget?.filters || []);
  const [limit, setLimit] = useState(initialWidget?.limit || 10);
  const [name, setName] = useState(initialWidget?.name || "");

  const needsField = type && type !== "stat";

  const canNext = () => {
    if (step === 1) return !!type;
    if (step === 2) return !needsField || !!field;
    if (step === 3) return !!name.trim();
    return false;
  };

  const handleCreate = () => {
    const widget = {
      type,
      name: name.trim(),
      filters: filters.filter((f) => f.field && f.op && f.value),
      field: needsField ? field : null,
      limit: needsField ? limit : null,
    };
    onCreate(widget);
  };

  return (
    <div className="wizard-overlay" onClick={onClose}>
      <div className="wizard-modal" onClick={(e) => e.stopPropagation()}>
        <header className="wizard-header">
          <h2>{isEditing ? "Edit Widget" : "Add Widget"}</h2>
          <span className="wizard-step-indicator">Step {step} of 3</span>
          <button className="wizard-close" onClick={onClose}>×</button>
        </header>

        <div className="wizard-body">
          {/* Step 1: Type */}
          {step === 1 && (
            <div className="wizard-step">
              <h3>What do you want to see?</h3>
              <div className="type-grid">
                {WIDGET_TYPES.map((wt) => (
                  <button
                    key={wt.value}
                    className={`type-card ${type === wt.value ? "selected" : ""}`}
                    onClick={() => setType(wt.value)}
                  >
                    <span className="type-icon">{wt.icon}</span>
                    <span className="type-label">{wt.label}</span>
                    <span className="type-desc">{wt.desc}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Step 2: Field + Filters */}
          {step === 2 && (
            <div className="wizard-step">
              {needsField && (
                <>
                  <h3>Which field to group by?</h3>
                  <select
                    className="wizard-select"
                    value={field}
                    onChange={(e) => setField(e.target.value)}
                  >
                    <option value="">Select a field…</option>
                    {schema.map((f) => (
                      <option key={f.name} value={f.name}>
                        {f.label}
                      </option>
                    ))}
                  </select>
                </>
              )}
              <h3 style={{ marginTop: needsField ? 16 : 0 }}>
                Filter the data (optional)
              </h3>
              <FilterBuilder
                schema={schema}
                filters={filters}
                onChange={setFilters}
                onClear={() => setFilters([])}
              />
            </div>
          )}

          {/* Step 3: Limit + Name + Size */}
          {step === 3 && (
            <div className="wizard-step">
              {needsField && (
                <>
                  <h3>Max values to show</h3>
                  <input
                    type="number"
                    className="wizard-input"
                    value={limit}
                    min={1}
                    max={200}
                    onChange={(e) => setLimit(Math.max(1, Math.min(200, Number(e.target.value) || 1)))}
                  />
                </>
              )}
              <h3 style={{ marginTop: needsField ? 16 : 0 }}>Widget name</h3>
              <input
                type="text"
                className="wizard-input"
                placeholder="e.g. Top Platforms"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
              />
            </div>
          )}
        </div>

        <footer className="wizard-footer">
          {step > 1 && (
            <button className="wizard-btn wizard-btn-back" onClick={() => setStep((s) => s - 1)}>
              ← Back
            </button>
          )}
          <div className="wizard-footer-spacer" />
          {step < 3 ? (
            <button
              className="wizard-btn wizard-btn-next"
              disabled={!canNext()}
              onClick={() => setStep((s) => s + 1)}
            >
              Next →
            </button>
          ) : (
            <button
              className="wizard-btn wizard-btn-create"
              disabled={!canNext()}
              onClick={handleCreate}
            >
              {isEditing ? "Save" : "Create Widget"}
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}

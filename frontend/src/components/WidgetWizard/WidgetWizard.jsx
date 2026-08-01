import React, { useState } from "react";
import { MAP_CENTER_OPTIONS } from "../../pages/Dashboard/widgets/countryLookup";
import "./WidgetWizard.css";

const WIDGET_TYPES = [
  { value: "stat", label: "Statistic", icon: "#️⃣", desc: "A single number — count of matching sessions" },
  { value: "pie", label: "Pie Chart", icon: "🥧", desc: "Distribution of values as proportional slices" },
  { value: "histogram", label: "Histogram", icon: "📊", desc: "Horizontal bar chart of value counts" },
  { value: "vertical_histogram", label: "Bar Chart", icon: "📊", desc: "Vertical bars of a number field sorted by value" },
  { value: "weighted_list", label: "Weighted List", icon: "📋", desc: "Ranked list with proportional bars" },
  { value: "map", label: "World Map", icon: "🗺️", desc: "Geographic session distribution by IP country" },
];

const ZOOM_LEVELS = [
  { value: 1, label: "1 — World view" },
  { value: 2, label: "2 — Continental" },
  { value: 3, label: "3 — Regional" },
  { value: 4, label: "4 — Country" },
  { value: 5, label: "5 — Detail" },
];

const DEFAULT_MAP_CONFIG = { centerCode: "FR", zoom: 3 };

export default function WidgetWizard({ schema, onClose, onCreate, initialWidget }) {
  const isEditing = !!initialWidget;
  const [step, setStep] = useState(isEditing ? 3 : 1);
  const [type, setType] = useState(initialWidget?.type || "");
  const [field, setField] = useState(initialWidget?.field || "");
  const [limit, setLimit] = useState(initialWidget?.limit || 10);
  const [name, setName] = useState(initialWidget?.name || "");
  const [mapConfig, setMapConfig] = useState(initialWidget?.mapConfig || DEFAULT_MAP_CONFIG);

  // stat has no field step; map has a locked field step; others have a free field step
  const needsField = type && type !== "stat";
  const fieldIsLocked = type === "map";

  const canNext = () => {
    if (step === 1) return !!type;
    if (step === 2) return fieldIsLocked || !!field;
    if (step === 3) return !!name.trim();
    return false;
  };

  const handleNext = () => {
    if (step === 1) {
      if (!needsField) {
        setStep(3); // stat skips field step
      } else {
        if (type === "map") setField("ip_country");
        setStep(2);
      }
    } else {
      setStep((s) => s + 1);
    }
  };

  const handleBack = () => {
    if (step === 3 && !needsField) {
      setStep(1); // stat came from step 1
    } else {
      setStep((s) => s - 1);
    }
  };

  const handleCreate = () => {
    const widget = {
      type,
      name: name.trim(),
      field: needsField ? field : null,
      limit: needsField && !fieldIsLocked ? limit : null,
      mapConfig: type === "map" ? mapConfig : undefined,
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

          {/* Step 2: Field selection */}
          {step === 2 && (
            <div className="wizard-step">
              <h3>Which field to group by?</h3>
              <select
                className={`wizard-select ${fieldIsLocked ? "wizard-select-locked" : ""}`}
                value={fieldIsLocked ? "ip_country" : field}
                disabled={fieldIsLocked}
                onChange={(e) => setField(e.target.value)}
              >
                {fieldIsLocked ? (
                  <option value="ip_country">IP Country Code</option>
                ) : (
                  <>
                    <option value="">Select a field…</option>
                    {(type === "vertical_histogram"
                      ? schema.filter((f) => f.type === "number")
                      : schema
                    ).map((f) => (
                      <option key={f.name} value={f.name}>
                        {f.label}
                      </option>
                    ))}
                  </>
                )}
              </select>
              {fieldIsLocked && (
                <p className="wizard-field-note">Field is fixed for Map widgets.</p>
              )}
            </div>
          )}

          {/* Step 3: Limit + Name + Map config */}
          {step === 3 && (
            <div className="wizard-step">
              {needsField && !fieldIsLocked && (
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
              {type === "map" && (
                <>
                  <h3>Center on</h3>
                  <select
                    className="wizard-select"
                    value={mapConfig.centerCode}
                    onChange={(e) => setMapConfig((prev) => ({ ...prev, centerCode: e.target.value }))}
                  >
                    {MAP_CENTER_OPTIONS.map((group) => (
                      <optgroup key={group.group} label={group.group}>
                        {group.options.map((o) => (
                          <option key={o.code} value={o.code}>{o.name}</option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                  <h3 style={{ marginTop: 16 }}>Zoom</h3>
                  <select
                    className="wizard-select"
                    value={mapConfig.zoom}
                    onChange={(e) => setMapConfig((prev) => ({ ...prev, zoom: Number(e.target.value) }))}
                  >
                    {ZOOM_LEVELS.map((z) => (
                      <option key={z.value} value={z.value}>{z.label}</option>
                    ))}
                  </select>
                </>
              )}
              <h3 style={{ marginTop: needsField || type === "map" ? 16 : 0 }}>Widget name</h3>
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
            <button className="wizard-btn wizard-btn-back" onClick={handleBack}>
              ← Back
            </button>
          )}
          <div className="wizard-footer-spacer" />
          {step < 3 ? (
            <button
              className="wizard-btn wizard-btn-next"
              disabled={!canNext()}
              onClick={handleNext}
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

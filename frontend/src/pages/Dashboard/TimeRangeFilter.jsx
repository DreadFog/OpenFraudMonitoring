import React from "react";

const OPTIONS = [
  { value: "24h", label: "24 hours" },
  { value: "7d", label: "7 days" },
  { value: "1m", label: "1 month" },
  { value: "custom", label: "Custom" },
];

export default function TimeRangeFilter({ range, defaultPreset, onChange }) {
  const mode = range?.mode || defaultPreset;
  const changeBound = (key, value) => {
    const next = { ...range, mode: "custom", [key]: value };
    if (key === "from" && value && next.to && value > next.to) next.to = "";
    if (key === "to" && value && next.from && value < next.from) next.from = "";
    onChange(next);
  };

  return (
    <div className="time-range-filter">
      <span className="time-range-title">Last seen</span>
      <div className="time-range-modes" role="group" aria-label="Last seen time range">
        {OPTIONS.map((option) => (
          <button key={option.value} type="button" className={mode === option.value ? "active" : ""} aria-pressed={mode === option.value} onClick={() => onChange(option.value === "custom" ? { mode: "custom", from: "", to: "" } : { mode: option.value })}>
            {option.label}
          </button>
        ))}
      </div>
      {mode === "custom" && (
        <div className="time-range-bounds">
          <label>From <input type="datetime-local" value={range?.from || ""} max={range?.to || undefined} onChange={(event) => changeBound("from", event.target.value)} /></label>
          <label>To <input type="datetime-local" value={range?.to || ""} min={range?.from || undefined} onChange={(event) => changeBound("to", event.target.value)} /></label>
        </div>
      )}
    </div>
  );
}
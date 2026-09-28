import React from "react";
import { widgetShade } from "./widgetShade";

export default function HistogramWidget({ groups, onValueClick, selectedValue, isBoolean, requiresFilterValue, onApply, onCancel }) {
  const max = Math.max(...groups.map((g) => g.count), 1);
  if (groups.length === 0) return <p className="empty-note">No data</p>;

  return (
    <div className="weighted-list">
      {groups.map((g, i) => selectedValue?.label === g.value ? (
        <div key={i} className="wl-item widget-filter-inline" aria-label={`Filter ${g.value}`}>
          <button type="button" onClick={() => onApply(false)}>{isBoolean ? "True" : "Include"}</button>
          <button type="button" onClick={() => onApply(true)}>{isBoolean ? "False" : "Exclude"}</button>
          <button type="button" className="widget-filter-cancel" onClick={onCancel} aria-label="Cancel" title="Cancel">×</button>
        </div>
      ) : (
        <button key={i} type="button" className="wl-item widget-value-button" style={{ "--row-color": widgetShade(g.count, groups, i) }} disabled={!onValueClick || g.value === "N/A" || g.value === "" || (requiresFilterValue && g.filter_value == null)} onClick={() => onValueClick(g.value, g.filter_value)} title={String(g.value)}>
          <div className="wl-bar" style={{ width: `${(g.count / max) * 100}%` }} />
          <span className="wl-rank">{i + 1}.</span>
          <span className="wl-value">{g.value}</span>
          <span className="wl-count">{g.count}</span>
        </button>
      ))}
    </div>
  );
}
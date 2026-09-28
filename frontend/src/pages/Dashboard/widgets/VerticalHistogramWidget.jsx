import React from "react";
import { widgetShade } from "./widgetShade";

export default function VerticalHistogramWidget({ groups, onValueClick }) {
  // Sort numerically ascending by value so bars go left→right in order
  const sorted = [...groups].sort((a, b) => Number(a.value) - Number(b.value));
  const max = Math.max(...sorted.map((g) => g.count), 1);

  if (sorted.length === 0) return <p className="empty-note">No data</p>;

  return (
    <div className="vhisto">
      {sorted.map((g, i) => (
        <button key={i} type="button" className="vhisto-col widget-value-button" style={{ "--row-color": widgetShade(g.count, groups, i) }} disabled={!onValueClick || g.value === "N/A" || g.value === ""} onClick={() => onValueClick(g.value)} title={`${g.value}: ${g.count} sessions`}>
          <div className="vhisto-bar-wrapper">
            <div
              className="vhisto-bar"
              style={{ height: `${Math.max(2, (g.count / max) * 100)}%` }}
            />
          </div>
          <span className="vhisto-label">{g.value}</span>
        </button>
      ))}
    </div>
  );
}

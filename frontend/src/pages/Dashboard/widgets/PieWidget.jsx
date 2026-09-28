import React from "react";
import { widgetShade } from "./widgetShade";

export default function PieWidget({ groups }) {
  const total = groups.reduce((s, g) => s + g.count, 0);
  if (total === 0) return <p className="empty-note">No data</p>;

  let cumPct = 0;
  const stops = groups.map((g, i) => {
    const pct = (g.count / total) * 100;
    const start = cumPct;
    cumPct += pct;
    return `${widgetShade(g.count, groups, i)} ${start}% ${cumPct}%`;
  });

  return (
    <div className="pie-wrapper">
      <div
        className="pie-circle"
        style={{ background: `conic-gradient(${stops.join(", ")})` }}
      />
      <div className="pie-legend">
        {groups.map((g, i) => (
          <div key={i} className="pie-legend-item">
            <span className="pie-swatch" style={{ background: widgetShade(g.count, groups, i) }} />
            <span className="pie-legend-label">{g.value}</span>
            <span className="pie-legend-count">{g.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

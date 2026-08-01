import React from "react";

const PALETTE = [
  "#58a6ff", "#f85149", "#f0883e", "#3fb950", "#bc8cff",
  "#79c0ff", "#d29922", "#ff7b72", "#56d364", "#e3b341",
];

export default function PieWidget({ groups }) {
  const total = groups.reduce((s, g) => s + g.count, 0);
  if (total === 0) return <p className="empty-note">No data</p>;

  let cumPct = 0;
  const stops = groups.map((g, i) => {
    const pct = (g.count / total) * 100;
    const start = cumPct;
    cumPct += pct;
    return `${PALETTE[i % PALETTE.length]} ${start}% ${cumPct}%`;
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
            <span className="pie-swatch" style={{ background: PALETTE[i % PALETTE.length] }} />
            <span className="pie-legend-label">{g.value}</span>
            <span className="pie-legend-count">{g.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

import React from "react";

const PALETTE = [
  "#58a6ff", "#f85149", "#f0883e", "#3fb950", "#bc8cff",
  "#79c0ff", "#d29922", "#ff7b72", "#56d364", "#e3b341",
];

export default function HistogramWidget({ groups }) {
  const max = Math.max(...groups.map((g) => g.count), 1);
  if (groups.length === 0) return <p className="empty-note">No data</p>;

  return (
    <div className="histogram">
      {groups.map((g, i) => (
        <div key={i} className="histo-row">
          <span className="histo-label">{g.value}</span>
          <div className="histo-bar-bg">
            <div
              className="histo-bar"
              style={{
                width: `${(g.count / max) * 100}%`,
                background: PALETTE[i % PALETTE.length],
              }}
            />
          </div>
          <span className="histo-count">{g.count}</span>
        </div>
      ))}
    </div>
  );
}

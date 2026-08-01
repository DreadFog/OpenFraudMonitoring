import React from "react";

export default function WeightedListWidget({ groups }) {
  const max = Math.max(...groups.map((g) => g.count), 1);
  if (groups.length === 0) return <p className="empty-note">No data</p>;

  return (
    <div className="weighted-list">
      {groups.map((g, i) => (
        <div key={i} className="wl-item">
          <div className="wl-bar" style={{ width: `${(g.count / max) * 100}%` }} />
          <span className="wl-rank">{i + 1}.</span>
          <span className="wl-value">{g.value}</span>
          <span className="wl-count">{g.count}</span>
        </div>
      ))}
    </div>
  );
}

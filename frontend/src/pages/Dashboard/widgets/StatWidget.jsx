import React from "react";

const STAT_COLORS = {
  "Total Sessions": "#58a6ff",
  "High Risk": "#f85149",
  "Bots Detected": "#f0883e",
  "Low Risk": "#3fb950",
};

export default function StatWidget({ data, widget }) {
  const color = STAT_COLORS[widget.name] || "#58a6ff";
  return (
    <div className="stat-num" style={{ color }}>
      {data.count ?? "—"}
    </div>
  );
}

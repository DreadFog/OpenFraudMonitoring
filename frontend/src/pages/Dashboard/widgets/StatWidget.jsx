import React from "react";
import { widgetShade } from "./widgetShade";

export default function StatWidget({ data, widget }) {
  return (
    <div className="stat-num" style={{ color: widget.color || widgetShade(data.count || 0, [{ count: data.count || 0 }], 0) }}>
      {data.count ?? "—"}
    </div>
  );
}

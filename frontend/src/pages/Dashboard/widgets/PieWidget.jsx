import React, { useState } from "react";
import { widgetShade } from "./widgetShade";

export default function PieWidget({ groups, onValueClick, selectedValue, requiresFilterValue }) {
  const [hoveredIndex, setHoveredIndex] = useState(null);
  const total = groups.reduce((sum, group) => sum + group.count, 0);
  if (total === 0) return <p className="empty-note">No data</p>;

  const canSelect = (group) => Boolean(onValueClick) && group.value != null &&
    group.value !== "N/A" && group.value !== "" &&
    (!requiresFilterValue || group.filter_value != null);
  let angle = -Math.PI / 2;
  const slices = groups.map((group) => {
    const start = angle;
    angle += (group.count / total) * Math.PI * 2;
    const midpoint = (start + angle) / 2;
    const point = (value) => `${100 + 100 * Math.cos(value)} ${100 + 100 * Math.sin(value)}`;
    return `M 100 100 L ${point(start)} A 100 100 0 0 1 ${point(midpoint)} A 100 100 0 0 1 ${point(angle)} Z`;
  });

  return (
    <div className="pie-wrapper" onPointerLeave={() => setHoveredIndex(null)}>
      <svg className="pie-circle" viewBox="0 0 200 200" role="group" aria-label="Pie chart">
        {groups.map((group, index) => group.count > 0 && (
          <path
            key={index}
            d={slices[index]}
            fill={widgetShade(group.count, groups, index)}
            style={{ "--slice-color": widgetShade(group.count, groups, index) }}
            className={`pie-slice ${canSelect(group) ? "pie-slice-interactive" : ""} ${hoveredIndex === index || selectedValue?.label === group.value ? "pie-slice-highlight" : ""}`}
            role={canSelect(group) ? "button" : "img"}
            tabIndex={canSelect(group) ? 0 : undefined}
            aria-label={`${group.value}: ${group.count}`}
            onPointerEnter={() => setHoveredIndex(index)}
            onPointerLeave={() => setHoveredIndex(null)}
            onFocus={() => setHoveredIndex(canSelect(group) ? index : null)}
            onBlur={() => setHoveredIndex(null)}
            onClick={() => canSelect(group) && onValueClick(group.value, group.filter_value)}
            onKeyDown={(event) => {
              if (canSelect(group) && (event.key === "Enter" || event.key === " ")) {
                event.preventDefault();
                onValueClick(group.value, group.filter_value);
              }
            }}
          >
            <title>{`${group.value}: ${group.count}`}</title>
          </path>
        ))}
      </svg>
      <div className="pie-legend">
        {groups.map((group, index) => (
          <button
            key={index}
            type="button"
            className={`pie-legend-item widget-value-button ${hoveredIndex === index || selectedValue?.label === group.value ? "pie-legend-highlight" : ""}`}
            style={{ "--row-color": widgetShade(group.count, groups, index) }}
            disabled={!canSelect(group)}
            onPointerEnter={() => setHoveredIndex(index)}
            onPointerLeave={() => setHoveredIndex(null)}
            onFocus={() => setHoveredIndex(index)}
            onBlur={() => setHoveredIndex(null)}
            onClick={() => onValueClick(group.value, group.filter_value)}
            title={`${group.value}: ${group.count}`}
          >
            <span className="pie-swatch" style={{ background: widgetShade(group.count, groups, index) }} />
            <span className="pie-legend-label">{group.value}</span>
            <span className="pie-legend-count">{group.count}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

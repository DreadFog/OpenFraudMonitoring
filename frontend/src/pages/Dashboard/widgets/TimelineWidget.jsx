import React, { useEffect, useRef, useState } from "react";

const UNITS = { minute: 60000, hour: 3600000, day: 86400000 };

function ruleColor(name) {
  let hash = 0;
  for (const character of name) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return `hsl(${hash % 360} 65% var(--timeline-lightness))`;
}

export default function TimelineWidget({ data, from, to, onValueClick }) {
  const [hoveredRule, setHoveredRule] = useState(null);
  const [plotWidth, setPlotWidth] = useState(0);
  const plotRef = useRef(null);

  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setPlotWidth(entry.contentRect.width));
    observer.observe(plotRef.current);
    return () => observer.disconnect();
  }, []);

  const unit = data.unit || "hour";
  const step = UNITS[unit];
  const totals = new Map();
  const names = new Set();
  for (const group of data.groups || []) {
    const start = new Date(group.bucket).getTime();
    if (!totals.has(start)) totals.set(start, []);
    totals.get(start).push(group);
    names.add(group.value);
  }
  const starts = [];
  for (let time = Math.floor(from / step) * step; time <= Math.floor(to / step) * step; time += step) starts.push(time);
  const max = Math.max(1, ...starts.map((start) => (totals.get(start) || []).reduce((sum, group) => sum + group.count, 0)));
  const axisTicks = [...new Set([0, Math.ceil(max / 4), Math.ceil(max / 2), Math.ceil(max * 3 / 4), max])];
  const visibleLabels = Math.max(1, Math.floor(plotWidth / 80));
  const labelEvery = visibleLabels > 1 ? Math.max(1, Math.ceil((starts.length - 1) / (visibleLabels - 1))) : 0;

  return (
    <div className="timeline-widget">
      <div className="timeline-plot">
        <div className="timeline-y-axis">
          <div className="timeline-y-scale">
            {axisTicks.map((tick) => (
              <span key={tick} className="timeline-y-label" style={{ bottom: `${tick / max * 100}%` }}>{tick}</span>
            ))}
          </div>
          <span className="timeline-y-caption">Events</span>
        </div>
        <div className="timeline-scroll" ref={plotRef}>
          <div className="timeline-columns">
            {starts.map((start, index) => {
              const groups = totals.get(start) || [];
              const total = groups.reduce((sum, group) => sum + group.count, 0);
              const date = new Date(start);
              const label = unit === "day" ? date.toLocaleDateString(undefined, { month: "short", day: "numeric" }) : date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
              return (
                <div key={start} className="timeline-column">
                  <div className="timeline-track" title={date.toLocaleString()}>
                    <div className="timeline-stack" style={{ height: `${total / max * 100}%` }}>
                      {groups.map((group) => (
                        <button
                          key={group.value}
                          type="button"
                          className={`timeline-segment ${hoveredRule === group.value ? "timeline-segment-active" : ""}`}
                          style={{ flexGrow: group.count, flexBasis: 0, background: ruleColor(group.value) }}
                          title={`${group.value}: ${group.count} matches (${date.toLocaleString()})`}
                          aria-label={`${group.value}: ${group.count} matches at ${date.toLocaleString()}`}
                          aria-haspopup="dialog"
                          disabled={!onValueClick}
                          onMouseEnter={() => setHoveredRule(group.value)}
                          onMouseLeave={() => setHoveredRule(null)}
                          onFocus={() => setHoveredRule(group.value)}
                          onBlur={() => setHoveredRule(null)}
                          onClick={() => onValueClick(group.value)}
                        >
                          {hoveredRule === group.value && <span className="timeline-segment-count">{group.count}</span>}
                        </button>
                      ))}
                    </div>
                  </div>
                  <span className="timeline-tick">
                    {(visibleLabels === 1 ? index === Math.floor(starts.length / 2) : index === 0 || index === starts.length - 1 || (index % labelEvery === 0 && starts.length - 1 - index >= labelEvery)) && (
                      <span className={`timeline-tick-label ${index === 0 && starts.length > 1 ? "timeline-tick-first" : ""} ${index === starts.length - 1 && starts.length > 1 ? "timeline-tick-last" : ""}`}>{label}</span>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
      {names.size > 0 ? (
        <div className="timeline-legend">
          {[...names].sort().map((name) => (
            <span key={name} className={`timeline-legend-item ${hoveredRule === name ? "timeline-legend-active" : ""}`}><span className="timeline-swatch" style={{ background: ruleColor(name) }} />{name}</span>
          ))}
        </div>
      ) : <span className="empty-note">No rule matches in this range</span>}
    </div>
  );
}
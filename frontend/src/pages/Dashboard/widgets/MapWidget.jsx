import React, { useMemo, useState, useCallback } from "react";
import { ComposableMap, Geographies, Geography } from "react-simple-maps";
import worldData from "world-atlas/countries-110m.json";
import { ALPHA2_TO_NUMERIC, COUNTRY_CENTROIDS, ZOOM_TO_SCALE } from "./countryLookup";
import { widgetShade } from "./widgetShade";

const DEFAULT_MAP_CONFIG = { centerCode: "WORLD", zoom: 1 };

export default function MapWidget({ data, mapConfig = DEFAULT_MAP_CONFIG, onValueClick }) {
  const groups = data?.groups || [];
  const [tooltip, setTooltip] = useState(null);

  const countMap = useMemo(() => {
    const map = {};
    groups.forEach((g, index) => {
      const numericId = ALPHA2_TO_NUMERIC[(g.value || "").toUpperCase()];
      if (numericId) map[numericId] = { color: widgetShade(g.count, groups, index), count: g.count, value: g.value };
    });
    return map;
  }, [groups]);

  const handleMouseEnter = useCallback((geo) => {
    const entry = countMap[geo.id];
    if (!entry) return;
    setTooltip({ name: geo.properties.name, count: entry.count });
  }, [countMap]);

  const handleMouseLeave = useCallback(() => setTooltip(null), []);

  const center = COUNTRY_CENTROIDS[mapConfig?.centerCode] || COUNTRY_CENTROIDS.WORLD;
  const scale = ZOOM_TO_SCALE[mapConfig?.zoom] || ZOOM_TO_SCALE[1];

  if (groups.length === 0) return <p className="empty-note">No data</p>;

  return (
    <div className="map-widget">
      <ComposableMap
        width={800}
        height={400}
        projectionConfig={{ scale, center }}
        style={{ width: "100%", height: "100%", display: "block" }}
        preserveAspectRatio="xMidYMid meet"
      >
        <Geographies geography={worldData}>
          {({ geographies }) =>
            geographies.map((geo) => {
              const entry = countMap[geo.id];
              const fill = entry?.color || "var(--raised)";
              return (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  fill={fill}
                  stroke="var(--bg)"
                  strokeWidth={0.4}
                  style={{
                    default: { outline: "none" },
                    hover: { outline: "none", fill: entry?.color || "var(--border)", filter: "brightness(1.15)" },
                    pressed: { outline: "none" },
                  }}
                  onMouseEnter={() => handleMouseEnter(geo)}
                  onMouseLeave={handleMouseLeave}
                  onClick={entry && onValueClick ? () => onValueClick(entry.value) : undefined}
                  onKeyDown={entry && onValueClick ? (event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onValueClick(entry.value);
                    }
                  } : undefined}
                  tabIndex={entry && onValueClick ? 0 : undefined}
                  role={entry && onValueClick ? "button" : undefined}
                  aria-label={entry && onValueClick ? `Filter ${geo.properties.name}: ${entry.count} sessions` : undefined}
                  cursor={entry && onValueClick ? "pointer" : "default"}
                />
              );
            })
          }
        </Geographies>
      </ComposableMap>
      {tooltip && (
        <div className="map-tooltip">
          <span className="map-tooltip-name">{tooltip.name}</span>
          <span className="map-tooltip-count">{tooltip.count} sessions</span>
        </div>
      )}
    </div>
  );
}

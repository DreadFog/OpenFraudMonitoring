import React, { useMemo, useState, useCallback } from "react";
import { ComposableMap, Geographies, Geography } from "react-simple-maps";
import worldData from "world-atlas/countries-110m.json";
import { ALPHA2_TO_NUMERIC, COUNTRY_CENTROIDS, ZOOM_TO_SCALE } from "./countryLookup";

const DEFAULT_MAP_CONFIG = { centerCode: "FR", zoom: 3 };

export default function MapWidget({ data, mapConfig = DEFAULT_MAP_CONFIG }) {
  const groups = data?.groups || [];
  const [tooltip, setTooltip] = useState(null);

  const countMap = useMemo(() => {
    const map = {};
    const max = Math.max(...groups.map((g) => g.count), 1);
    groups.forEach((g) => {
      const numericId = ALPHA2_TO_NUMERIC[(g.value || "").toUpperCase()];
      if (numericId) map[numericId] = { intensity: g.count / max, count: g.count };
    });
    return map;
  }, [groups]);

  const handleMouseEnter = useCallback((geo) => {
    const entry = countMap[geo.id];
    if (!entry) return;
    setTooltip({ name: geo.properties.name, count: entry.count });
  }, [countMap]);

  const handleMouseLeave = useCallback(() => setTooltip(null), []);

  const center = COUNTRY_CENTROIDS[mapConfig?.centerCode] || COUNTRY_CENTROIDS.FR;
  const scale = ZOOM_TO_SCALE[mapConfig?.zoom] || ZOOM_TO_SCALE[3];

  if (groups.length === 0) return <p className="empty-note">No data</p>;

  return (
    <div className="map-widget">
      <ComposableMap
        projectionConfig={{ scale, center }}
        style={{ width: "100%", height: "100%", display: "block" }}
        preserveAspectRatio="xMidYMid slice"
      >
        <Geographies geography={worldData}>
          {({ geographies }) =>
            geographies.map((geo) => {
              const entry = countMap[geo.id];
              const intensity = entry?.intensity || 0;
              const fill = intensity > 0
                ? `rgba(88, 166, 255, ${Math.max(0.2, intensity)})`
                : "#21262d";
              const hoverFill = intensity > 0
                ? `rgba(120, 190, 255, ${Math.max(0.3, Math.min(1, intensity + 0.2))})`
                : "#2d333b";
              return (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  fill={fill}
                  stroke="#0d1117"
                  strokeWidth={0.4}
                  style={{
                    default: { outline: "none" },
                    hover: { outline: "none", fill: hoverFill },
                    pressed: { outline: "none" },
                  }}
                  onMouseEnter={() => handleMouseEnter(geo)}
                  onMouseLeave={handleMouseLeave}
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

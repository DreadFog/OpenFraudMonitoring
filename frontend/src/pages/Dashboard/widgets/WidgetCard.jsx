import React from "react";
import StatWidget from "./StatWidget";
import PieWidget from "./PieWidget";
import HistogramWidget from "./HistogramWidget";
import WeightedListWidget from "./WeightedListWidget";
import VerticalHistogramWidget from "./VerticalHistogramWidget";
import MapWidget from "./MapWidget";

export default function WidgetCard({ widget, data, editMode, onEdit, onRemove }) {
  const renderContent = () => {
    if (!data) return <span className="widget-loading">…</span>;

    if (widget.type === "stat") return <StatWidget data={data} widget={widget} />;

    const groups = data.groups || [];
    if (widget.type === "pie") return <PieWidget groups={groups} />;
    if (widget.type === "histogram") return <HistogramWidget groups={groups} />;
    if (widget.type === "weighted_list") return <WeightedListWidget groups={groups} />;
    if (widget.type === "vertical_histogram") return <VerticalHistogramWidget groups={groups} />;
    if (widget.type === "map") return <MapWidget data={data} mapConfig={widget.mapConfig} />;
    return null;
  };

  return (
    <div className={`widget-card ${editMode ? "widget-edit-mode" : ""}`}>
      {editMode && (
        <div className="widget-toolbar">
          <button className="widget-tb-btn widget-tb-edit" onClick={onEdit} title="Edit widget">✎</button>
          <button className="widget-tb-btn widget-tb-delete" onClick={onRemove} title="Delete widget">×</button>
        </div>
      )}
      <div className="widget-content">{renderContent()}</div>
      <div className="stat-label">{widget.name}</div>
    </div>
  );
}

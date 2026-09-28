import React, { useEffect, useRef, useState } from "react";
import StatWidget from "./StatWidget";
import PieWidget from "./PieWidget";
import HistogramWidget from "./HistogramWidget";
import VerticalHistogramWidget from "./VerticalHistogramWidget";
import MapWidget from "./MapWidget";
import TimelineWidget from "./TimelineWidget";

export default function WidgetCard({ widget, data, editMode, onEdit, onRemove, onFilter, schema = [], timeWindow }) {
  const [selectedValue, setSelectedValue] = useState(null);
  const panelRef = useRef(null);
  const field = widget.type === "map" ? "ip_country" : widget.type === "timeline" ? "triggered_flag" : widget.field;
  const fieldDef = schema.find((entry) => entry.name === field);

  useEffect(() => {
    if (selectedValue === null) return;
    const dismiss = (event) => {
      if (event.key === "Escape" || (event.type === "mousedown" && !panelRef.current?.contains(event.target) && !event.target.closest(".widget-filter-inline"))) {
        setSelectedValue(null);
      }
    };
    document.addEventListener("mousedown", dismiss);
    document.addEventListener("keydown", dismiss);
    return () => {
      document.removeEventListener("mousedown", dismiss);
      document.removeEventListener("keydown", dismiss);
    };
  }, [selectedValue]);

  const applyFilter = (exclude) => {
    const isBoolean = fieldDef.type === "boolean";
    const value = isBoolean ? (exclude ? "false" : "true") : String(selectedValue.filterValue);
    onFilter({ field, op: exclude && !isBoolean ? "neq" : "eq", value });
    setSelectedValue(null);
  };

  const selectValue = (value, filterValue) => {
    if (!editMode && fieldDef && fieldDef.type !== "date" && value != null && value !== "N/A" && value !== "" && (field !== "ip_as" || filterValue != null)) {
      setSelectedValue({ label: value, filterValue: filterValue ?? value });
    }
  };

  const onValueClick = !editMode && fieldDef && fieldDef.type !== "date" ? selectValue : undefined;

  const renderContent = () => {
    if (!data) return <span className="widget-loading">…</span>;

    if (widget.type === "stat") return <StatWidget data={data} widget={widget} />;

    const groups = data.groups || [];
    if (widget.type === "pie") return <PieWidget groups={groups} />;
    if (widget.type === "histogram" || widget.type === "weighted_list") return <HistogramWidget groups={groups} onValueClick={onValueClick} selectedValue={selectedValue} isBoolean={fieldDef?.type === "boolean"} requiresFilterValue={field === "ip_as"} onApply={applyFilter} onCancel={() => setSelectedValue(null)} />;
    if (widget.type === "vertical_histogram") return <VerticalHistogramWidget groups={groups} onValueClick={onValueClick} />;
    if (widget.type === "map") return <MapWidget data={data} mapConfig={widget.mapConfig} onValueClick={onValueClick} />;
    if (widget.type === "timeline") return <TimelineWidget data={data} from={timeWindow.from} to={timeWindow.to} onValueClick={onValueClick} />;
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
      {selectedValue !== null && widget.type !== "histogram" && widget.type !== "weighted_list" && (
        <div className="widget-filter-overlay" ref={panelRef} role="dialog" aria-label={`Filter ${String(selectedValue.label)}`}>
          <button type="button" className="widget-filter-close" onClick={() => setSelectedValue(null)} aria-label="Close filter options">×</button>
          <div className="widget-filter-value" title={String(selectedValue.label)}>{String(selectedValue.label)}</div>
          <div className="widget-filter-actions">
            <button type="button" onClick={() => applyFilter(false)}>{fieldDef?.type === "boolean" ? "True" : "Include"}</button>
            <button type="button" onClick={() => applyFilter(true)}>{fieldDef?.type === "boolean" ? "False" : "Exclude"}</button>
          </div>
        </div>
      )}
    </div>
  );
}

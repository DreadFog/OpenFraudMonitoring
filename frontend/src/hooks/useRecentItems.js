import { useCallback } from "react";
import { usePersistentState } from "./usePersistentState";

const MAX_ITEMS = 8;

/** Recently viewed sessions/devices/entities/graphs, shown on the landing page. */
export function useRecentItems() {
  const [items, setItems] = usePersistentState("recent.items", []);
  const record = useCallback((item) => {
    setItems((prev) => [
      { ...item, ts: Date.now() },
      ...(Array.isArray(prev) ? prev : []).filter((i) => i.key !== item.key),
    ].slice(0, MAX_ITEMS));
  }, [setItems]);
  return [Array.isArray(items) ? items : [], record];
}

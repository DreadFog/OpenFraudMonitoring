export const TIME_RANGE_DURATIONS = {
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
  "1m": 30 * 24 * 60 * 60 * 1000,
};

export function resolveTimeRange(range, defaultPreset, now) {
  const duration = TIME_RANGE_DURATIONS[defaultPreset] || TIME_RANGE_DURATIONS["24h"];
  const preset = TIME_RANGE_DURATIONS[range?.mode];
  if (preset) return { from: now - preset, to: now };

  const from = range?.from ? new Date(range.from).getTime() : null;
  const to = range?.to ? new Date(range.to).getTime() : null;
  if (range?.mode !== "custom" || (!Number.isFinite(from) && !Number.isFinite(to))) {
    return { from: now - duration, to: now };
  }
  const end = Number.isFinite(to) ? to : from + duration;
  return { from: Number.isFinite(from) ? from : end - duration, to: end };
}
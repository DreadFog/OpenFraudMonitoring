export function widgetShade(count, groups, index) {
  const counts = groups.map((group) => group.count);
  const min = Math.min(...counts);
  const max = Math.max(...counts);
  const strength = max === min ? 0.5 : (count - min) / (max - min);
  const lightness = (0.76 - strength * 0.33).toFixed(3);
  return `oklch(${lightness} 0.13 var(--widget-hue-${index % 5 + 1}))`;
}
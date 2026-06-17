const CLASS_COLORS: Record<string, string> = {
  low: "#ffeda0",
  moderate: "#feb24c",
  high: "#f03b20",
  critical: "#800026",
};

export function heatClassColor(heatClass: string): string {
  return CLASS_COLORS[heatClass] ?? "#888888";
}

export function lstColor(lst: number, min = 30, max = 50): string {
  const t = Math.max(0, Math.min(1, (lst - min) / (max - min)));
  const r = Math.round(255 * t);
  const g = Math.round(200 * (1 - t));
  const b = Math.round(80 * (1 - t));
  return `rgb(${r},${g},${b})`;
}

export const CLASS_LABELS: Record<string, string> = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
  critical: "Critical",
};

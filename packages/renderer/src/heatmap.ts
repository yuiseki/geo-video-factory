/** Default thermal-like palette suited for dark satellite basemaps. */
export const DEFAULT_HEATMAP_COLORS: [number, string][] = [
  [0, 'rgba(0, 0, 0, 0)'],
  [0.15, 'rgba(14, 165, 233, 0.45)'],
  [0.4, 'rgba(56, 189, 248, 0.78)'],
  [0.65, 'rgba(250, 204, 21, 0.88)'],
  [0.85, 'rgba(249, 115, 22, 0.95)'],
  [1, 'rgba(239, 68, 68, 1)'],
];

/** Build a MapLibre `heatmap-color` interpolate expression. */
export function heatmapColorExpression(stops: [number, string][] = DEFAULT_HEATMAP_COLORS): unknown[] {
  if (stops.length < 2) {
    throw new Error('heatmap colors require at least 2 [density, color] stops');
  }
  const expr: unknown[] = ['interpolate', ['linear'], ['heatmap-density']];
  let prev = -Infinity;
  for (const [stop, color] of stops) {
    if (!(stop > prev)) {
      throw new Error('heatmap color stops must be strictly ascending');
    }
    prev = stop;
    expr.push(stop, color);
  }
  return expr;
}

/** Build a MapLibre `heatmap-weight` value or expression. */
export function heatmapWeightExpression(weightProperty?: string): number | unknown[] {
  if (!weightProperty) return 1;
  return ['coalesce', ['to-number', ['get', weightProperty], 0], 0];
}

/** Build a zoom-scaled MapLibre `heatmap-radius` expression around a base radius at z10. */
export function heatmapRadiusExpression(baseRadius = 26): unknown[] {
  return [
    'interpolate',
    ['linear'],
    ['zoom'],
    7, Math.max(4, Math.round(baseRadius * 0.5)),
    10, baseRadius,
    13, Math.round(baseRadius * 1.6),
  ];
}

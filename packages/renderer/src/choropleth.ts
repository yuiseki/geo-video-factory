// Pure MapLibre expression builders and break calculators for 2D/3D choropleths.

export type ChoroplethScale = 'step' | 'linear';

export function choroplethColorExpression(
  property: string,
  breaks: number[],
  colors: string[],
  scale: ChoroplethScale = 'step',
  noDataColor = '#6b7280',
): unknown[] {
  if (!breaks.length) throw new Error('choropleth requires at least one break');
  if (breaks.length !== colors.length) {
    throw new Error(`choropleth breaks (${breaks.length}) and colors (${colors.length}) length mismatch`);
  }
  for (let i = 1; i < breaks.length; i++) {
    if (breaks[i]! <= breaks[i - 1]!) {
      throw new Error('choropleth breaks must be strictly ascending');
    }
  }
  const valueExpr = ['get', property];
  const colorExpr: unknown[] =
    scale === 'linear'
      ? ['interpolate', ['linear'], valueExpr, ...breaks.flatMap((b, i) => [b, colors[i]!])]
      : ['step', valueExpr, colors[0]!, ...breaks.slice(1).flatMap((b, i) => [b, colors[i + 1]!])];

  // Keep null/missing/non-numeric features visually distinct from numeric 0.
  return ['case', ['==', ['typeof', valueExpr], 'number'], colorExpr, noDataColor];
}

export function choroplethHeightExpression(
  property: string,
  heightScale = 1,
  heightBase = 0,
  progress = 1,
): unknown[] {
  const scale = heightScale * Math.max(0, Math.min(1, progress));
  const valueExpr = ['get', property];
  return [
    'case',
    ['==', ['typeof', valueExpr], 'number'],
    ['max', 0, ['*', ['-', valueExpr, heightBase], scale]],
    0,
  ];
}

export function computeEqualBreaks(values: number[], classes: number): number[] {
  const valid = values.filter((v) => Number.isFinite(v));
  if (!valid.length || classes < 1) return [];
  const min = Math.min(...valid);
  const max = Math.max(...valid);
  const step = classes === 1 ? 0 : (max - min) / classes;
  return Array.from({ length: classes }, (_, i) => min + i * step);
}

export function computeQuantileBreaks(values: number[], classes: number): number[] {
  const sorted = values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (!sorted.length || classes < 1) return [];
  const at = (q: number): number => {
    const pos = q * (sorted.length - 1);
    const lo = Math.floor(pos);
    const hi = Math.ceil(pos);
    return lo === hi ? sorted[lo]! : sorted[lo]! + (sorted[hi]! - sorted[lo]!) * (pos - lo);
  };
  return Array.from({ length: classes }, (_, i) => at(i / classes));
}

export interface ChoroplethLegendItem {
  color: string;
  label: string;
}

function formatLegendValue(value: number, divisor = 1): string {
  const scaled = divisor !== 1 ? value / divisor : value;
  const rounded = Math.round(scaled * 100) / 100;
  return rounded.toLocaleString('en-US');
}

export function buildChoroplethLegendItems(options: {
  breaks: number[];
  colors: string[];
  scale?: ChoroplethScale;
  noDataColor?: string;
  unit?: string;
  labels?: string[];
  showNoData?: boolean;
  noDataLabel?: string;
  valueDivisor?: number;
}): ChoroplethLegendItem[] {
  const {
    breaks,
    colors,
    scale = 'step',
    noDataColor = '#6b7280',
    unit = '',
    labels,
    showNoData = false,
    noDataLabel = 'データなし',
    valueDivisor = 1,
  } = options;
  const items: ChoroplethLegendItem[] = colors.map((color, i) => {
    if (labels?.[i]) return { color, label: labels[i]! };
    const start = formatLegendValue(breaks[i] ?? 0, valueDivisor);
    if (scale === 'linear') {
      return { color, label: `${start}${unit}` };
    }
    if (i < breaks.length - 1) {
      const end = formatLegendValue(breaks[i + 1]!, valueDivisor);
      return { color, label: `${start}〜${end}${unit}` };
    }
    return { color, label: `${start}${unit}〜` };
  });
  if (showNoData) {
    items.push({ color: noDataColor, label: noDataLabel });
  }
  return items;
}

export interface ChoroplethLabelPoint {
  at: [number, number];
  text: string;
  value: number | null;
  properties?: Record<string, unknown>;
}

function ringAreaAndCentroid(ring: number[][]): { area: number; centroid: [number, number] } {
  if (ring.length < 3) {
    const p = ring[0] ?? [0, 0];
    return { area: 0, centroid: [p[0] ?? 0, p[1] ?? 0] };
  }
  let twiceArea = 0;
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    const [x0, y0] = ring[i]!;
    const [x1, y1] = ring[i + 1]!;
    const cross = (x0 ?? 0) * (y1 ?? 0) - (x1 ?? 0) * (y0 ?? 0);
    twiceArea += cross;
    cx += ((x0 ?? 0) + (x1 ?? 0)) * cross;
    cy += ((y0 ?? 0) + (y1 ?? 0)) * cross;
  }
  if (Math.abs(twiceArea) < 1e-12) {
    const sum = ring.reduce<[number, number]>((acc, p) => [acc[0] + (p[0] ?? 0), acc[1] + (p[1] ?? 0)], [0, 0]);
    return { area: 0, centroid: [sum[0] / ring.length, sum[1] / ring.length] };
  }
  return { area: Math.abs(twiceArea) / 2, centroid: [cx / (3 * twiceArea), cy / (3 * twiceArea)] };
}

export function extractChoroplethLabelPoints(
  geojson: unknown,
  labelProperty: string,
  valueProperty: string,
): ChoroplethLabelPoint[] {
  const fc = geojson as { features?: Array<{ properties?: Record<string, unknown>; geometry?: { type?: string; coordinates?: unknown } }> };
  if (!Array.isArray(fc?.features)) return [];
  const points: ChoroplethLabelPoint[] = [];
  for (const f of fc.features) {
    const rawLabel = f.properties?.[labelProperty];
    if (rawLabel === null || rawLabel === undefined || rawLabel === '') continue;
    const rawVal = f.properties?.[valueProperty];
    const value = typeof rawVal === 'number' && Number.isFinite(rawVal) ? rawVal : null;
    const geom = f.geometry;
    let centroid: [number, number] | null = null;
    if (geom?.type === 'Polygon' && Array.isArray(geom.coordinates)) {
      const outer = geom.coordinates[0] as number[][] | undefined;
      if (outer?.length) centroid = ringAreaAndCentroid(outer).centroid;
    } else if (geom?.type === 'MultiPolygon' && Array.isArray(geom.coordinates)) {
      let bestArea = -1;
      for (const poly of geom.coordinates as number[][][][]) {
        const outer = poly[0];
        if (!outer?.length) continue;
        const res = ringAreaAndCentroid(outer);
        if (res.area >= bestArea) {
          bestArea = res.area;
          centroid = res.centroid;
        }
      }
    }
    if (centroid) points.push({ at: centroid, text: String(rawLabel), value, properties: f.properties });
  }
  return points;
}

export function choroplethExtrusionHeight(
  value: number | null,
  heightScale = 1,
  heightBase = 0,
  progress = 1,
): number {
  if (value === null || !Number.isFinite(value)) return 0;
  const clamped = Math.max(0, Math.min(1, progress));
  return Math.max(0, (value - heightBase) * heightScale * clamped);
}

const EARTH_CIRCUMFERENCE_M = 40075016.68557849;

export function extrusionScreenOffsetY(
  altitudeMeters: number,
  latDeg: number,
  zoom: number,
  pitchDeg: number,
): number {
  if (altitudeMeters <= 0 || pitchDeg <= 0) return 0;
  const metersPerPixel =
    (EARTH_CIRCUMFERENCE_M * Math.cos((latDeg * Math.PI) / 180)) / (512 * Math.pow(2, zoom));
  return -(altitudeMeters / metersPerPixel) * Math.sin((pitchDeg * Math.PI) / 180);
}

export function choroplethLabelFontSize(
  value: number | null,
  minVal: number,
  maxVal: number,
  minSize: number,
  maxSize: number,
  progress = 1,
): number {
  if (value === null || !Number.isFinite(value) || maxSize <= minSize || maxVal <= minVal) return minSize;
  const ratio = Math.max(0, Math.min(1, (value - minVal) / (maxVal - minVal)));
  const clamped = Math.max(0, Math.min(1, progress));
  return minSize + (maxSize - minSize) * ratio * clamped;
}

export function choroplethLabelOpacity(
  baseAlpha: number,
  progress: number,
  hasRise: boolean,
  value: number | null = null,
  minVal = 0,
  maxVal = 0,
  minOpacity = 0.35,
): number {
  const riseFactor = hasRise ? Math.max(0, Math.min(1, progress)) : 1;
  let valueFactor = 1;
  if (value !== null && Number.isFinite(value) && maxVal > minVal) {
    const ratio = Math.max(0, Math.min(1, (value - minVal) / (maxVal - minVal)));
    valueFactor = minOpacity + (1 - minOpacity) * ratio;
  }
  return baseAlpha * riseFactor * valueFactor;
}

export function choroplethDimMultiplier(
  t: number,
  window?: [number, number],
  dimOpacity = 0.15,
): number {
  if (!window) return 1;
  const [t0, t1] = window;
  if (t <= t0) return 1;
  if (t >= t1 || t1 <= t0) return dimOpacity;
  const u = (t - t0) / (t1 - t0);
  return 1 + (dimOpacity - 1) * u;
}

export function choroplethFocusFilters(
  property: string,
  values: (string | number)[],
): { focusFilter: unknown[]; dimFilter: unknown[] } {
  const focusFilter: unknown[] = ['in', ['get', property], ['literal', values]];
  return { focusFilter, dimFilter: ['!', focusFilter] };
}

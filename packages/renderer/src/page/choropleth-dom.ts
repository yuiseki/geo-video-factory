import {
  buildChoroplethLegendItems,
  choroplethDimMultiplier,
  choroplethExtrusionHeight,
  choroplethLabelFontSize,
  choroplethLabelOpacity,
  extractChoroplethLabelPoints,
  extrusionScreenOffsetY,
  type ChoroplethLabelPoint,
} from '../choropleth.js';
import { ease } from '../lib.js';
import type { ChoroplethOverlay, ShotSpec } from '../types.js';
import type { MapLibreMap } from './map-types.js';

const labelCache = new Map<string, ChoroplethLabelPoint[]>();

function cacheKey(o: ChoroplethOverlay): string {
  return `${o.src ?? ''}|${o.labelProperty ?? ''}|${o.property}`;
}

export async function preloadChoroplethLabels(spec: ShotSpec): Promise<void> {
  labelCache.clear();
  const tasks: Promise<void>[] = [];
  for (const shot of spec.shots) {
    for (const o of shot.overlays || []) {
      if (o.type !== 'choropleth' || !o.labelProperty) continue;
      const key = cacheKey(o);
      if (labelCache.has(key)) continue;
      if (o.data) {
        labelCache.set(key, extractChoroplethLabelPoints(o.data, o.labelProperty, o.property));
      } else if (o.src) {
        const url = '/' + o.src.replace(/^\/+/, '');
        tasks.push(
          fetch(url)
            .then((r) => (r.ok ? r.json() : null))
            .then((gj) => {
              if (gj) labelCache.set(key, extractChoroplethLabelPoints(gj, o.labelProperty!, o.property));
            }),
        );
      }
    }
  }
  await Promise.all(tasks);
}

export function choroplethRiseProgress(o: ChoroplethOverlay, t: number): number {
  if (!o.extrude || !o.rise) return 1;
  const span = o.rise[1] - o.rise[0];
  if (span <= 0) return t >= o.rise[0] ? 1 : 0;
  return ease('out', Math.max(0, Math.min(1, (t - o.rise[0]) / span)));
}

export function drawChoroplethLegend(
  o: ChoroplethOverlay,
  a: number,
  hasSub: boolean,
  el: (cls: string, html: string, style?: Record<string, string | number>) => HTMLDivElement,
  esc: (s: string) => string,
): void {
  const cfg = typeof o.legend === 'object' ? o.legend : {};
  const items = buildChoroplethLegendItems({
    breaks: o.breaks,
    colors: o.colors,
    scale: o.scale,
    noDataColor: o.noDataColor,
    unit: cfg.unit,
    labels: cfg.labels,
    showNoData: cfg.showNoData,
    noDataLabel: cfg.noDataLabel,
    valueDivisor: cfg.valueDivisor,
  });
  const pos = cfg.position ?? 'bottom-left';
  const style: Record<string, string | number> = { opacity: a };
  style[pos.startsWith('top') ? 'top' : 'bottom'] = pos.startsWith('bottom') && hasSub ? '204px' : '32px';
  style[pos.endsWith('left') ? 'left' : 'right'] = '32px';
  const titleHtml = cfg.title ? `<div class="legend-title">${esc(cfg.title)}</div>` : '';
  const rowsHtml = items
    .map(
      (item) =>
        `<div class="legend-row"><span class="legend-swatch" style="background:${esc(item.color)}"></span><span>${esc(item.label)}</span></div>`,
    )
    .join('');
  el('legend', `${titleHtml}<div class="legend-items">${rowsHtml}</div>`, style);
}

function projectAtAltitude(
  lngLat: [number, number],
  altitudeMeters: number,
  map: MapLibreMap,
): { x: number; y: number } {
  const base = map.project(lngLat);
  const dy = extrusionScreenOffsetY(altitudeMeters, lngLat[1], map.getZoom(), map.getPitch());
  return { x: base.x, y: base.y + dy };
}

export function drawChoroplethLabels(
  o: ChoroplethOverlay,
  t: number,
  a: number,
  map: MapLibreMap,
  scaleValue: number,
  el: (cls: string, html: string, style?: Record<string, string | number>) => HTMLDivElement,
  esc: (s: string) => string,
): void {
  if (!o.labelProperty) return;
  const pts = labelCache.get(cacheKey(o));
  if (!pts?.length) return;
  const progress = choroplethRiseProgress(o, t);
  const focusProp = o.focus?.property ?? o.labelProperty;
  const focusSet = o.focus ? new Set(o.focus.values) : null;
  const dim = o.focus ? choroplethDimMultiplier(t, o.focus.window, o.focus.dimOpacity) : 1;
  const minFont = o.labelFontSize ?? 22;
  const maxFont = o.labelMaxFontSize ?? minFont;
  const vals = pts.map((p) => p.value).filter((v): v is number => v !== null && Number.isFinite(v));
  const minVal = vals.length ? Math.min(...vals) : 0;
  const maxVal = vals.length ? Math.max(...vals) : 0;
  for (const pt of pts) {
    const alt = o.extrude ? choroplethExtrusionHeight(pt.value, o.heightScale ?? 1, o.heightBase ?? 0, progress) : 0;
    const screen = projectAtAltitude(pt.at, alt, map);
    const fontSize = choroplethLabelFontSize(pt.value, minVal, maxVal, minFont, maxFont, progress);
    const isFocused = !focusSet || focusSet.has(pt.properties?.[focusProp] as string | number);
    const labelAlpha =
      choroplethLabelOpacity(a, progress, !!(o.extrude && o.rise), pt.value, minVal, maxVal) * (isFocused ? 1 : dim);
    el('choropleth-label', esc(pt.text), {
      left: screen.x / scaleValue + 'px',
      top: screen.y / scaleValue + 'px',
      fontSize: fontSize + 'px',
      opacity: labelAlpha,
    });
  }
}

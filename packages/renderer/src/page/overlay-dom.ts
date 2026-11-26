import { ease } from '../lib.js';
import type { ShotSpec } from '../types.js';
import type { MapLibreMap } from './map-types.js';

/** What every overlay drawer shares: the map, the shot spec, the DOM layers and the current time. */
export const ov = {
  map: undefined as unknown as MapLibreMap,
  spec: undefined as unknown as ShotSpec,
  overlayEl: undefined as unknown as HTMLElement,
  tintEl: undefined as unknown as HTMLElement,
  nowSec: 0,
};

export function configureOverlayRenderer(context: {
  map: MapLibreMap;
  spec: ShotSpec;
  overlayEl: HTMLElement;
  tintEl: HTMLElement;
}): void {
  Object.assign(ov, context);
}

export function setOverlayTime(sec: number): void {
  ov.nowSec = sec;
}

/** CSS pixels per 1920-wide design pixel. */
export const scale = () => (ov.spec.width ?? 1920) / 1920;

export function el(cls: string, html: string, style: Record<string, string | number> = {}): HTMLDivElement {
  const d = document.createElement('div');
  d.className = 'o ' + cls;
  d.innerHTML = html;
  Object.assign(d.style, style);
  ov.overlayEl.appendChild(d);
  return d;
}

export const esc = (s: string) =>
  String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c] ?? c));

export const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
export const outCubic = (x: number) => ease('out', x);

/** Seconds since the overlay's window opened and until it closes, and whether it is open. */
export type Phase = { since: number; until: number; on: boolean };
/** Entry progress 0..1 over dur seconds after delay. */
export type Inn = (dur: number, delay?: number) => number;

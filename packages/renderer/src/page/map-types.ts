import type { LngLat } from '../types.js';

export interface MapLibreMap {
  once: (event: string, cb: () => void) => void;
  triggerRepaint: () => void;
  jumpTo: (cam: { center: LngLat; zoom: number; pitch: number; bearing: number }) => void;
  setTerrain: (t: unknown) => void;
  setLayoutProperty: (id: string, prop: string, val: unknown) => void;
  setPaintProperty: (id: string, prop: string, val: unknown) => void;
  getSource: (id: string) => { setData: (data: unknown) => void };
  project: (lngLat: LngLat) => { x: number; y: number };
  setPadding: (padding: { top: number; right: number; bottom: number; left: number }) => void;
  setVerticalFieldOfView: (fov: number) => void;
  getZoom: () => number;
  getPitch: () => number;
}


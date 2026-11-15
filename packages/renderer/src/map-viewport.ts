export type LngLat = readonly [number, number];

export interface Viewport {
  width: number;
  height: number;
  padding: number;
}

export interface FlatCamera {
  center: [number, number];
  zoom: number;
}

const TILE_SIZE = 512;
const MAX_LATITUDE = 85.051129;

function mercator(point: LngLat): [number, number] {
  const longitude = (point[0] + 180) / 360;
  const latitude = Math.max(-MAX_LATITUDE, Math.min(MAX_LATITUDE, point[1])) * Math.PI / 180;
  return [longitude, (1 - Math.asinh(Math.tan(latitude)) / Math.PI) / 2];
}

function inverseMercator(point: LngLat): [number, number] {
  return [point[0] * 360 - 180, Math.atan(Math.sinh(Math.PI * (1 - 2 * point[1]))) * 180 / Math.PI];
}

function availableSize(viewport: Viewport): [number, number] {
  const width = viewport.width - 2 * viewport.padding;
  const height = viewport.height - 2 * viewport.padding;
  if (width <= 0 || height <= 0) throw new Error('viewport padding leaves no drawable area');
  return [width, height];
}

export function fitLngLatBounds(points: readonly LngLat[], viewport: Viewport): FlatCamera {
  if (points.length < 2) throw new Error('at least two points are required to fit bounds');
  const projected = points.map(mercator);
  const xs = projected.map(([x]) => x);
  const ys = projected.map(([, y]) => y);
  const west = Math.min(...xs);
  const east = Math.max(...xs);
  const north = Math.min(...ys);
  const south = Math.max(...ys);
  const [width, height] = availableSize(viewport);
  const spanX = east - west;
  const spanY = south - north;
  const worldSize = Math.min(spanX === 0 ? Infinity : width / spanX, spanY === 0 ? Infinity : height / spanY);
  if (!Number.isFinite(worldSize)) throw new Error('bounds must contain at least two distinct locations');
  return {
    center: inverseMercator([(west + east) / 2, (north + south) / 2]),
    zoom: Math.log2(worldSize / TILE_SIZE),
  };
}

export function projectLngLat(point: LngLat, camera: FlatCamera, viewport: Viewport): { x: number; y: number } {
  const [x, y] = mercator(point);
  const [centerX, centerY] = mercator(camera.center);
  const worldSize = TILE_SIZE * 2 ** camera.zoom;
  return {
    x: viewport.width / 2 + (x - centerX) * worldSize,
    y: viewport.height / 2 + (y - centerY) * worldSize,
  };
}

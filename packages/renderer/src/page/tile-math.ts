// Pure helpers behind the custom tile protocols (no browser APIs, so they can be unit-tested in Node).

export const tile2lng = (x: number, z: number): number => (x / 2 ** z) * 360 - 180;
export const tile2lat = (y: number, z: number): number => {
  const n = Math.PI - (2 * Math.PI * y) / 2 ** z;
  return (180 / Math.PI) * Math.atan(Math.sinh(n));
};

export function parseImgTileUrl(url: string): { id: string; z: number; x: number; y: number } {
  const match = url.match(/^imgtile:\/\/([^/]+)\/(\d+)\/(\d+)\/(\d+)/);
  if (!match) throw new Error(`invalid imgtile url: ${url}`);
  return { id: match[1]!, z: Number(match[2]), x: Number(match[3]), y: Number(match[4]) };
}

/** Where a bbox image lands inside the 256px tile, or null when the bbox does not touch the tile. */
export function imageTileRect(
  z: number,
  x: number,
  y: number,
  bbox: [number, number, number, number],
): { x: number; y: number; w: number; h: number } | null {
  const [w, s, e, n] = bbox;
  const tw = tile2lng(x, z);
  const te = tile2lng(x + 1, z);
  const tn = tile2lat(y, z);
  const ts = tile2lat(y + 1, z);
  if (e < tw || w > te || n < ts || s > tn) return null;
  const px = (lng: number) => ((lng - tw) / (te - tw)) * 256;
  const py = (lat: number) => ((tn - lat) / (tn - ts)) * 256;
  return { x: px(w), y: py(n), w: px(e) - px(w), h: py(s) - py(n) };
}

/** "no data" is pure black in old photos and flat gray (52,52,52) in the low-zoom world mosaic. */
export function isNoDataPixel(r: number, g: number, b: number): boolean {
  return (r < 10 && g < 10 && b < 10) || (Math.abs(r - 52) <= 3 && Math.abs(g - 52) <= 3 && Math.abs(b - 52) <= 3);
}

/** Make no-data pixels transparent in place; returns how many were cleared. */
export function clearNoDataPixels(d: Uint8ClampedArray): number {
  let cleared = 0;
  for (let i = 0; i < d.length; i += 4) {
    if (isNoDataPixel(d[i]!, d[i + 1]!, d[i + 2]!)) {
      d[i + 3] = 0;
      cleared++;
    }
  }
  return cleared;
}

import * as maplibregl from 'maplibre-gl';
import { gsiToTerrarium, terrariumRGB } from '../lib.js';

function registerGsiDem(): void {
  maplibregl.addProtocol('gsidem', async (params, abort) => {
    const url = params.url.replace('gsidem://', 'https://');
    const res = await fetch(url, { signal: abort.signal });
    const canvas = new OffscreenCanvas(256, 256);
    const ctx = canvas.getContext('2d', { willReadFrequently: true })!;
    const out = ctx.createImageData(256, 256);
    if (res.ok) {
      const bmp = await createImageBitmap(await res.blob());
      ctx.drawImage(bmp, 0, 0);
      const src = ctx.getImageData(0, 0, 256, 256).data;
      for (let i = 0; i < src.length; i += 4) {
        const [r, g, b] = terrariumRGB(gsiToTerrarium(src[i]!, src[i + 1]!, src[i + 2]!));
        out.data[i] = r;
        out.data[i + 1] = g;
        out.data[i + 2] = b;
        out.data[i + 3] = 255;
      }
    } else {
      // 404 = outside the tiled area: flat 0 m
      for (let i = 0; i < out.data.length; i += 4) {
        out.data[i] = 128;
        out.data[i + 3] = 255;
      }
    }
    ctx.putImageData(out, 0, 0);
    const blob = await canvas.convertToBlob({ type: 'image/png' });
    return { data: await blob.arrayBuffer() };
  });
}

// Old photo tiles in JPEG paint "no data" black (sea, gaps between flights). Make near-black transparent
// so the current photo shows through instead of black holes.
function registerClearBlack(): void {
  maplibregl.addProtocol('gsiclear', async (params, abort) => {
    const res = await fetch(params.url.replace('gsiclear://', 'https://'), { signal: abort.signal });
    if (!res.ok) {
      const empty = new OffscreenCanvas(256, 256);
      empty.getContext('2d');
      return { data: await (await empty.convertToBlob({ type: 'image/png' })).arrayBuffer() };
    }
    const bmp = await createImageBitmap(await res.blob());
    const canvas = new OffscreenCanvas(256, 256);
    const ctx = canvas.getContext('2d', { willReadFrequently: true })!;
    ctx.drawImage(bmp, 0, 0);
    const img = ctx.getImageData(0, 0, 256, 256);
    const d = img.data;
    // "no data" is pure black in old photos and flat gray (52,52,52) in the low-zoom world mosaic
    for (let i = 0; i < d.length; i += 4) {
      const r = d[i]!;
      const g = d[i + 1]!;
      const b = d[i + 2]!;
      if ((r < 10 && g < 10 && b < 10) || (Math.abs(r - 52) <= 3 && Math.abs(g - 52) <= 3 && Math.abs(b - 52) <= 3)) {
        d[i + 3] = 0;
      }
    }
    ctx.putImageData(img, 0, 0);
    return { data: await (await canvas.convertToBlob({ type: 'image/png' })).arrayBuffer() };
  });
}

const IMAGES: Record<string, { src: string; bbox: [number, number, number, number]; bitmap?: Promise<ImageBitmap> }> = {};
const tile2lng = (x: number, z: number) => (x / 2 ** z) * 360 - 180;
const tile2lat = (y: number, z: number) => {
  const n = Math.PI - (2 * Math.PI * y) / 2 ** z;
  return (180 / Math.PI) * Math.atan(Math.sinh(n));
};

function registerImageTiles(): void {
  maplibregl.addProtocol('imgtile', async (params) => {
    const match = params.url.match(/^imgtile:\/\/([^/]+)\/(\d+)\/(\d+)\/(\d+)/);
    if (!match) throw new Error(`invalid imgtile url: ${params.url}`);
    const id = match[1]!;
    const z = Number(match[2]);
    const x = Number(match[3]);
    const y = Number(match[4]);
    const im = IMAGES[id]!;
    im.bitmap ??= fetch(im.src)
      .then((r) => {
        if (!r.ok) throw new Error(`image ${im.src}: HTTP ${r.status}`);
        return r.blob();
      })
      .then(createImageBitmap);
    const bmp = await im.bitmap;
    const [w, s, e, n] = im.bbox;
    const tw = tile2lng(x, z);
    const te = tile2lng(x + 1, z);
    const tn = tile2lat(y, z);
    const ts = tile2lat(y + 1, z);
    const canvas = new OffscreenCanvas(256, 256);
    const ctx = canvas.getContext('2d')!;
    const px = (lng: number) => ((lng - tw) / (te - tw)) * 256;
    const py = (lat: number) => ((tn - lat) / (tn - ts)) * 256;
    if (!(e < tw || w > te || n < ts || s > tn)) ctx.drawImage(bmp, px(w), py(n), px(e) - px(w), py(s) - py(n));
    return { data: await (await canvas.convertToBlob({ type: 'image/png' })).arrayBuffer() };
  });
}

export function registerMapProtocols(): void {
  registerGsiDem();
  registerClearBlack();
  registerImageTiles();
}

export function registerImageOverlay(id: string, src: string, bbox: [number, number, number, number]): void {
  IMAGES[id] = { src, bbox };
}

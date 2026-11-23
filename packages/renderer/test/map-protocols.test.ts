import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { registerImageOverlay, registerMapProtocols } from '../src/page/map-protocols.js';
import { gsiToTerrarium, terrariumRGB } from '../src/lib.js';

type Handler = (params: { url: string }, abort: AbortController) => Promise<{ data: ArrayBuffer }>;
const handlers = new Map<string, Handler>();

interface Draw { args: number[] }
let draws: Draw[] = [];
let fetches: string[] = [];
let bitmaps = 0;

const g = globalThis as Record<string, unknown>;
const saved: Record<string, unknown> = {};

// "PNG" = the raw RGBA bytes, so tests can read back what a handler produced.
class FakeCanvas {
  pixels: Uint8ClampedArray;
  constructor(public w: number, public h: number) {
    this.pixels = new Uint8ClampedArray(w * h * 4);
  }
  getContext() {
    const canvas = this;
    return {
      createImageData: (w: number, h: number) => ({ data: new Uint8ClampedArray(w * h * 4) }),
      drawImage: (bmp: { pixels?: Uint8ClampedArray }, ...args: number[]) => {
        if (bmp.pixels) canvas.pixels = new Uint8ClampedArray(bmp.pixels);
        draws.push({ args });
      },
      getImageData: () => ({ data: new Uint8ClampedArray(canvas.pixels) }),
      putImageData: (img: { data: Uint8ClampedArray }) => { canvas.pixels = new Uint8ClampedArray(img.data); },
    };
  }
  async convertToBlob() {
    const bytes = this.pixels;
    return { arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) };
  }
}

const tileOf = (fill: [number, number, number, number] | null) => {
  const px = new Uint8ClampedArray(256 * 256 * 4);
  if (fill) for (let i = 0; i < px.length; i += 4) px.set(fill, i);
  return px;
};
const read = (r: { data: ArrayBuffer }) => new Uint8ClampedArray(r.data);

function stubFetch(responses: Record<string, { ok: boolean; pixels?: Uint8ClampedArray }>) {
  g.fetch = async (url: string) => {
    fetches.push(String(url));
    const hit = Object.entries(responses).find(([k]) => String(url).includes(k))?.[1] ?? { ok: false };
    return { ok: hit.ok, status: hit.ok ? 200 : 404, blob: async () => ({ pixels: hit.pixels }) };
  };
}

beforeEach(() => {
  for (const k of ['OffscreenCanvas', 'createImageBitmap', 'fetch']) saved[k] = g[k];
  handlers.clear();
  draws = [];
  fetches = [];
  bitmaps = 0;
  g.OffscreenCanvas = FakeCanvas;
  g.createImageBitmap = async (blob: { pixels?: Uint8ClampedArray }) => { bitmaps++; return { pixels: blob.pixels }; };
  registerMapProtocols(((name: string, h: Handler) => { handlers.set(name, h); }) as never);
});
afterEach(() => { for (const [k, v] of Object.entries(saved)) g[k] = v; });

const run = (name: string, url: string) => handlers.get(name)!({ url }, new AbortController());

test('registers the three custom protocols', () => {
  assert.deepEqual([...handlers.keys()].sort(), ['gsidem', 'gsiclear', 'imgtile'].sort());
});

test('gsidem: fetches over https and re-encodes elevations as terrarium', async () => {
  // R=0,G=1,B=0 -> x=256 -> 2.56 m
  stubFetch({ 'dem_png/10/1/2': { ok: true, pixels: tileOf([0, 1, 0, 255]) } });
  const out = read(await run('gsidem', 'gsidem://cyberjapandata.gsi.go.jp/xyz/dem_png/10/1/2.png'));
  assert.equal(fetches[0], 'https://cyberjapandata.gsi.go.jp/xyz/dem_png/10/1/2.png');
  const [r, gg, b] = terrariumRGB(gsiToTerrarium(0, 1, 0));
  assert.deepEqual([...out.slice(0, 4)], [r, gg, b, 255]);
  assert.deepEqual([...out.slice(-4)], [r, gg, b, 255]);
});

test('gsidem: no-data pixels become 0 m and a 404 tile is flat 0 m (terrarium 128,0,0)', async () => {
  stubFetch({ nodata: { ok: true, pixels: tileOf([128, 0, 0, 255]) } });
  const [r0, g0, b0] = terrariumRGB(0);
  const nodata = read(await run('gsidem', 'gsidem://h/nodata'));
  assert.deepEqual([...nodata.slice(0, 4)], [r0, g0, b0, 255]);
  const missing = read(await run('gsidem', 'gsidem://h/missing'));
  assert.deepEqual([...missing.slice(0, 4)], [128, 0, 0, 255]);
  assert.equal(missing.length, 256 * 256 * 4);
  assert.equal(bitmaps, 1, 'a 404 does not decode an image');
});

test('gsiclear: black and mosaic-gray pixels turn transparent, photo pixels are kept', async () => {
  const px = tileOf([200, 120, 60, 255]);
  px.set([0, 0, 0, 255], 0);
  px.set([52, 52, 52, 255], 4);
  stubFetch({ photo: { ok: true, pixels: px } });
  const out = read(await run('gsiclear', 'gsiclear://h/photo.jpg'));
  assert.deepEqual([...out.slice(0, 8)], [0, 0, 0, 0, 52, 52, 52, 0]);
  assert.deepEqual([...out.slice(8, 12)], [200, 120, 60, 255]);
});

test('gsiclear: a missing tile is an empty transparent tile', async () => {
  stubFetch({});
  const out = read(await run('gsiclear', 'gsiclear://h/none.jpg'));
  assert.equal(out.every((v) => v === 0), true);
});

test('imgtile: draws the image at the bbox position and decodes the file only once for many tiles', async () => {
  registerImageOverlay('ov-test', '/assets/map.png', [-180, -85.0511287798, 180, 85.0511287798]);
  stubFetch({ 'assets/map.png': { ok: true, pixels: tileOf([10, 20, 30, 255]) } });
  await run('imgtile', 'imgtile://ov-test/0/0/0');
  await run('imgtile', 'imgtile://ov-test/1/0/0');
  await run('imgtile', 'imgtile://ov-test/1/1/1');
  assert.deepEqual(fetches, ['/assets/map.png']);
  assert.equal(bitmaps, 1);
  assert.equal(draws.length, 3);
  assert.ok(Math.abs(draws[0]!.args[2]! - 256) < 1e-6, 'z0 tile: full width');
  assert.ok(Math.abs(draws[1]!.args[2]! - 512) < 1e-6, 'z1 tile: world is twice the tile');
});

test('imgtile: a tile outside the bbox is blank and the image is not drawn', async () => {
  registerImageOverlay('ov-small', '/assets/s.png', [139, 35, 140, 36]);
  stubFetch({ 's.png': { ok: true, pixels: tileOf([1, 2, 3, 255]) } });
  const out = read(await run('imgtile', 'imgtile://ov-small/1/0/0'));
  assert.equal(draws.length, 0);
  assert.equal(out.every((v) => v === 0), true);
});

test('imgtile: failures name the file or the url', async () => {
  registerImageOverlay('ov-missing', '/assets/missing.png', [0, 0, 1, 1]);
  stubFetch({});
  await assert.rejects(run('imgtile', 'imgtile://ov-missing/0/0/0'), /missing\.png: HTTP 404/);
  await assert.rejects(run('imgtile', 'imgtile://bad-url'), /invalid imgtile url/);
});

test('perf budget: converting a 256x256 elevation tile takes well under 200 ms', async () => {
  stubFetch({ dem: { ok: true, pixels: tileOf([0, 100, 200, 255]) } });
  const t0 = performance.now();
  for (let i = 0; i < 10; i++) await run('gsidem', 'gsidem://h/dem');
  const per = (performance.now() - t0) / 10;
  assert.ok(per < 200, `${per.toFixed(0)} ms per tile`);
});

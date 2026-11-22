import { test } from 'node:test';
import assert from 'node:assert/strict';
import { analyzeTextureTone } from '../src/page/plateau-texture-tone.js';

const tex = (data: Uint8ClampedArray | Uint8Array | undefined, extra: object = {}) => ({ image: { data, ...extra } }) as never;
const solid = (r: number, g: number, b: number, a = 255, px = 64) => {
  const d = new Uint8ClampedArray(px * 4);
  for (let i = 0; i < px; i++) d.set([r, g, b, a], i * 4);
  return d;
};

test('analyzeTextureTone: missing texture or pixels is neutral', () => {
  assert.deepEqual(analyzeTextureTone(null), { tone: 1, bland: false });
  assert.deepEqual(analyzeTextureTone(undefined), { tone: 1, bland: false });
  assert.deepEqual(analyzeTextureTone({ image: null } as never), { tone: 1, bland: false });
  assert.deepEqual(analyzeTextureTone(tex(undefined, { width: 0, height: 0 })), { tone: 1, bland: false });
});

test('analyzeTextureTone: fully transparent pixels are ignored', () => {
  assert.deepEqual(analyzeTextureTone(tex(solid(255, 255, 255, 0))), { tone: 1, bland: false });
});

test('analyzeTextureTone: washed-out white is toned down hardest, mid-bright less, dark not at all', () => {
  assert.equal(analyzeTextureTone(tex(solid(255, 255, 255))).tone, 0.64);
  assert.equal(analyzeTextureTone(tex(solid(170, 170, 170))).tone, 0.78);
  assert.equal(analyzeTextureTone(tex(solid(60, 60, 60))).tone, 1);
});

test('analyzeTextureTone: flat mid-gray is bland, a contrasty atlas is not', () => {
  assert.equal(analyzeTextureTone(tex(solid(120, 120, 120))).bland, true);
  const d = new Uint8ClampedArray(64 * 4);
  for (let i = 0; i < 64; i++) d.set(i % 2 ? [20, 20, 20, 255] : [200, 200, 200, 255], i * 4);
  assert.equal(analyzeTextureTone(tex(d)).bland, false);
});

test('analyzeTextureTone: result is cached per texture object', () => {
  const t = tex(solid(255, 255, 255));
  assert.equal(analyzeTextureTone(t), analyzeTextureTone(t));
});

test('perf budget: analysing a 2048x2048 atlas stays under 1 s', () => {
  const px = 2048 * 2048;
  const d = new Uint8ClampedArray(px * 4).fill(180);
  const t0 = performance.now();
  analyzeTextureTone(tex(d));
  const ms = performance.now() - t0;
  assert.ok(ms < 1000, `took ${ms.toFixed(0)} ms`);
});

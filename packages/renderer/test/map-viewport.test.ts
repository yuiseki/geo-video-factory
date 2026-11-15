import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fitLngLatBounds, projectLngLat } from '../src/map-viewport.js';

const HORMUZ: [number, number] = [56.4, 26.4];
const TOKYO: [number, number] = [139.7671, 35.6812];

test('fitLngLatBounds keeps both endpoints inside the requested viewport padding', () => {
  const viewport = { width: 640, height: 360, padding: 80 };
  const camera = fitLngLatBounds([HORMUZ, TOKYO], viewport);

  for (const point of [HORMUZ, TOKYO] as const) {
    const screen = projectLngLat(point, camera, viewport);
    assert.ok(screen.x >= viewport.padding && screen.x <= viewport.width - viewport.padding, `${point} x=${screen.x}`);
    assert.ok(screen.y >= viewport.padding && screen.y <= viewport.height - viewport.padding, `${point} y=${screen.y}`);
  }
  assert.ok(camera.zoom > 2 && camera.zoom < 2.1, `unexpected zoom ${camera.zoom}`);
});

test('fitLngLatBounds uses the Web Mercator midpoint rather than an arithmetic latitude midpoint', () => {
  const camera = fitLngLatBounds([HORMUZ, TOKYO], { width: 640, height: 360, padding: 80 });
  assert.ok(Math.abs(camera.center[0] - 98.08355) < 1e-6);
  assert.ok(Math.abs(camera.center[1] - 31.1540786) < 1e-6, `unexpected latitude ${camera.center[1]}`);
});

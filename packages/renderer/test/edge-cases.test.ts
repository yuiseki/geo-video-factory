import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { buildChoroplethLegendItems, extractChoroplethLabelPoints } from '../src/choropleth.js';
import { cameraAt, gsiToTerrarium, locate, terrariumRGB } from '../src/lib.js';
import { fitLngLatBounds, projectLngLat } from '../src/map-viewport.js';
import { configureOverlayRenderer, drawOverlays } from '../src/page/overlays.js';
import { preloadChoroplethLabels } from '../src/page/choropleth-dom.js';
import { fakeMap, installFakeDocument } from './support/fake-dom.js';
import type { Shot, ShotSpec } from '../src/types.js';

test('legend: custom labels win, linear scale prints the break value, step scale prints ranges', () => {
  const custom = buildChoroplethLegendItems({ breaks: [0, 10], colors: ['#111', '#222'], labels: ['低', '高'] });
  assert.deepEqual(custom.map((i) => i.label), ['低', '高']);
  const linear = buildChoroplethLegendItems({ breaks: [0, 1500], colors: ['#111', '#222'], scale: 'linear', unit: '人' });
  assert.deepEqual(linear.map((i) => i.label), ['0人', '1,500人']);
  const step = buildChoroplethLegendItems({ breaks: [0, 10, 20], colors: ['#1', '#2', '#3'], showNoData: true, noDataLabel: '欠測' });
  assert.equal(step.length, 4);
  assert.equal(step.at(-1)!.label, '欠測');
  assert.ok(step[0]!.label.includes('10'));
});

test('label points: degenerate rings fall back to a vertex or the vertex mean instead of NaN', () => {
  const fc = {
    features: [
      { properties: { n: 'one' }, geometry: { type: 'Polygon', coordinates: [[[5, 6]]] } },
      { properties: { n: 'line' }, geometry: { type: 'Polygon', coordinates: [[[0, 0], [2, 0], [4, 0], [0, 0]]] } },
      { properties: { n: 'empty' }, geometry: { type: 'Polygon', coordinates: [[]] } },
      { properties: { n: '' }, geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1]]] } },
      { properties: { n: 'nogeom' } },
      { properties: { n: 'multi' }, geometry: { type: 'MultiPolygon', coordinates: [[[[0, 0], [1, 0], [1, 1], [0, 0]]], [[[10, 10], [20, 10], [20, 20], [10, 20], [10, 10]]]] } },
    ],
  };
  const pts = extractChoroplethLabelPoints(fc, 'n', 'v');
  const by = Object.fromEntries(pts.map((p) => [p.text, p.at]));
  assert.deepEqual(by.one, [5, 6]);
  assert.ok(Math.abs(by.line![0] - 1.5) < 1e-9 && by.line![1] === 0);
  assert.ok(!('empty' in by) && !('nogeom' in by));
  assert.deepEqual(by.multi!.map((x) => Math.round(x)), [15, 15], 'largest part wins');
  for (const p of pts) assert.ok(p.at.every(Number.isFinite));
  assert.deepEqual(extractChoroplethLabelPoints(null, 'n', 'v'), []);
  assert.deepEqual(extractChoroplethLabelPoints({ features: 'x' }, 'n', 'v'), []);
});

test('gsiToTerrarium handles the negative range and terrariumRGB keeps sub-metre precision', () => {
  // x = 2^24 - 100 -> -1.00 m
  const x = 16777216 - 100;
  assert.equal(gsiToTerrarium(x >> 16, (x >> 8) & 255, x & 255), -1);
  const [r, g, b] = terrariumRGB(10.5);
  assert.equal(r * 256 + g + b / 256 - 32768, 10.5);
  assert.deepEqual(terrariumRGB(-0.5).length, 3);
});

test('cameraAt with one key holds it (defaults for pitch and bearing) and rejects zero keys; locate copes with no shots', () => {
  const k = { t: 0, center: [1, 2] as [number, number], zoom: 5 };
  assert.deepEqual(cameraAt([k as never], 0.7), { center: [1, 2], zoom: 5, pitch: 0, bearing: 0 });
  assert.throws(() => cameraAt([], 0), /at least one key/);
  assert.deepEqual(locate([], 3), { index: 0, t: 0, sec: 0 });
  assert.deepEqual(locate([{ duration: 0 }], 3), { index: 0, t: 0, sec: 0 });
});

test('fitLngLatBounds and projectLngLat reject impossible input', () => {
  const vp = { width: 100, height: 100, padding: 10 };
  assert.throws(() => fitLngLatBounds([[0, 0]], vp), /at least two points/);
  assert.throws(() => fitLngLatBounds([[0, 0], [1, 1]], { width: 20, height: 100, padding: 10 }), /no drawable area/);
  assert.throws(() => fitLngLatBounds([[3, 3], [3, 3]], vp), /two distinct locations/);
  // a vertical-only or horizontal-only pair still fits
  assert.ok(Number.isFinite(fitLngLatBounds([[0, 0], [0, 5]], vp).zoom));
  assert.ok(Number.isFinite(fitLngLatBounds([[0, 0], [5, 0]], vp).zoom));
  // latitude is clamped at the Mercator limit instead of going infinite
  assert.ok(Number.isFinite(projectLngLat([0, 90], { center: [0, 0], zoom: 2 }, vp).y));
  // the camera centre projects to the viewport centre
  assert.deepEqual(projectLngLat([10, 20], { center: [10, 20], zoom: 3 }, vp), { x: 50, y: 50 });
});

let dom: ReturnType<typeof installFakeDocument>;
beforeEach(() => { dom = installFakeDocument(); });
afterEach(() => dom.restore());

function overlayRun(shot: Shot, t: number, pass: 'map' | 'dom', extra: Partial<ShotSpec> = {}) {
  const spec = { shots: [shot], width: 960, height: 540, ...extra } as ShotSpec;
  const { map } = fakeMap();
  configureOverlayRenderer({ map: map as never, spec, overlayEl: dom.overlay as never, tintEl: dom.tint as never });
  drawOverlays(0, shot, t, pass);
  return dom.overlay.children;
}

test('overlays: a choropleth draws its legend and labels in the dom pass only while visible', async () => {
  const data = { features: [{ properties: { n: 'A', v: 1 }, geometry: { type: 'Polygon', coordinates: [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]] } }] };
  const o = { type: 'choropleth', data, property: 'v', breaks: [0, 5], colors: ['#111', '#eee'], labelProperty: 'n', legend: true, show: [0.2, 0.8] } as never;
  const shot: Shot = { duration: 4, overlays: [o] };
  await preloadChoroplethLabels({ shots: [shot] } as never);
  assert.deepEqual(overlayRun(shot, 0.5, 'dom').map((c) => c.className), ['o choropleth-label', 'o legend']);
  assert.deepEqual(overlayRun(shot, 0.9, 'dom').map((c) => c.className), []);
});

test('overlays: a label given a screen position (no map point) uses design coordinates', () => {
  const shot: Shot = { duration: 4, overlays: [{ type: 'label', text: 'x', screen: [300, 400], dot: true }] };
  const els = overlayRun(shot, 0.9, 'dom');
  assert.equal(els[0]!.style.left, '300px');
  assert.equal(els[0]!.style.top, '400px');
  assert.ok(els[0]!.innerHTML.includes('class="dot"'));
});

test('overlays: panel motions, photo-marker labels and plain quotes take their own branches', () => {
  for (const motion of ['still', 'in', 'out', 'up', 'down', undefined]) {
    const els = overlayRun({ duration: 8, overlays: [{ type: 'panel', src: 'a.jpg', motion, show: [0, 1] } as never] }, 0.5, 'dom');
    assert.ok(els[0]!.innerHTML.includes('scale('), String(motion));
  }
  const marker = overlayRun({ duration: 4, overlays: [{ type: 'photo_marker', src: 'p.jpg', at: [1, 1], cameraAt: [2, 2], cameraLabel: 'cam', cameraLabelAnchor: 'start', bridgeAt: [3, 3], bridgeLabel: 'br' } as never] }, 0.9, 'dom');
  assert.ok(marker[0]!.innerHTML.includes('text-anchor="start"'));
  assert.ok(marker[0]!.innerHTML.includes('>br<'));
  const quote = overlayRun({ duration: 4, overlays: [{ type: 'quote', text: 'q', marks: false, date: '2020' } as never] }, 0.9, 'dom');
  assert.equal(quote[0]!.className, 'o quote plain');
});

test('overlays: a chapter that is not on leaves the tint untouched and the leader dips below for downward offsets', () => {
  const late: Shot = { duration: 4, overlays: [{ type: 'chapter', text: 'c', show: [0.5, 0.9] }] };
  overlayRun(late, 0.1, 'map');
  assert.equal(dom.tint.style.opacity, '0');
  const leader = overlayRun({ duration: 4, overlays: [{ type: 'label', text: 'x', at: [1, 1], offset: [10, 50], leader: true }] }, 0.9, 'dom');
  assert.ok(leader[0]!.innerHTML.includes('<path'));
});

test('overlays: tint from the shot itself survives and counters accept text values and count-up', () => {
  const shot: Shot = { duration: 4, tint: 0.4, overlays: [{ type: 'counter', value: '約100', caption: 'c', prefix: '¥', countUp: undefined } as never, { type: 'counter', value: 1000, countUp: [0, 0.5], from: 100, decimals: 1 } as never] };
  overlayRun(shot, 0.9, 'map');
  assert.equal(dom.tint.style.opacity, '0.4');
  const els = overlayRun(shot, 0.25, 'dom');
  assert.ok(els[0]!.innerHTML.includes('約100'));
  assert.ok(els[0]!.innerHTML.includes('class="pre"'));
  assert.ok(/\d/.test(els[1]!.innerHTML));
});

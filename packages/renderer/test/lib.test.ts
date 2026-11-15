import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
  gsiToTerrarium,
  demSourceSpec,
  ease,
  cameraAt,
  sliceLine,
  locate,
  fadeAlpha,
  wrapSubtitle,
  layoutLines,
  estimateSeconds,
  phase,
  easeOutBack,
  typeCount,
  chartGeometry,
} from '../src/lib.js';
import { parseWav, writeWav } from '../src/voice.js';
import { countValue, counterNumber, odometerColumns } from '../src/counter.js';
import type { CameraKey } from '../src/types.js';

test('GSI DEM: positive, negative and NA pixels', () => {
  const x = 377612;
  assert.equal(gsiToTerrarium(x >> 16, (x >> 8) & 255, x & 255), 3776.12);
  const n = 2 ** 24 - 150;
  assert.equal(gsiToTerrarium(n >> 16, (n >> 8) & 255, n & 255), -1.5);
  assert.equal(gsiToTerrarium(128, 0, 0), 0);
});

test('demSourceSpec builds raster-dem config for gsi and mapterhorn', () => {
  const gsi = demSourceSpec('gsi');
  assert.equal(gsi.source.type, 'raster-dem');
  assert.equal(gsi.source.tileSize, 256);
  assert.equal(gsi.source.encoding, 'terrarium');
  assert.match(gsi.source.tiles[0]!, /^gsidem:\/\//);

  const mh = demSourceSpec('mapterhorn');
  assert.equal(mh.source.type, 'raster-dem');
  assert.equal(mh.source.tileSize, 512);
  assert.equal(mh.source.encoding, 'terrarium');
  assert.equal(mh.source.tiles[0], 'https://tiles.mapterhorn.com/{z}/{x}/{y}.webp');
  assert.match(mh.credit, /Mapterhorn/);

  assert.throws(() => demSourceSpec('unknown-dem'));
});

test('ease keeps ends and is monotonic', () => {
  for (const k of ['linear', 'inOut', 'in', 'out'] as const) {
    assert.equal(ease(k, 0), 0);
    assert.equal(ease(k, 1), 1);
    assert.ok(ease(k, 0.6) >= ease(k, 0.4));
  }
});

test('cameraAt interpolates keys and takes the short way round for bearing', () => {
  const keys: CameraKey[] = [
    { t: 0, center: [138, 35], zoom: 10, pitch: 0, bearing: 350 },
    { t: 1, center: [139, 36], zoom: 12, pitch: 60, bearing: 10 },
  ];
  const mid = cameraAt(keys, 0.5, 'linear');
  assert.equal(mid.zoom, 11);
  assert.equal(mid.pitch, 30);
  assert.ok(Math.abs(((mid.bearing % 360) + 360) % 360) < 1e-9 || Math.abs(mid.bearing - 360) < 1e-9);
  assert.ok(Math.abs(mid.center[0] - 138.5) < 1e-9);
  assert.deepEqual(cameraAt(keys, 1, 'linear').center, [139, 36]);
});

test('cameraAt with fly path couples zoom and pan (van Wijk) without high-zoom skidding', () => {
  const zoomIn: CameraKey[] = [
    { t: 0, center: [98.08355, 31.1540786], zoom: 2.01733745 },
    { t: 1, center: [139.7671, 35.6812], zoom: 10 },
  ];
  assert.deepEqual(cameraAt(zoomIn, 0, 'linear', { path: 'fly', width: 640, height: 360 }).center, zoomIn[0]!.center);
  assert.deepEqual(cameraAt(zoomIn, 1, 'linear', { path: 'fly', width: 640, height: 360 }).center, zoomIn[1]!.center);
  const halfIn = cameraAt(zoomIn, 0.5, 'linear', { path: 'fly', width: 640, height: 360 });
  // By halfway through a zoom-in flight, the camera should already be centered near Tokyo instead of inland China.
  assert.ok(halfIn.center[0] > 138, `expected center lng > 138 at t=0.5, got ${halfIn.center[0]}`);
  assert.ok(halfIn.zoom < 7, `expected zoom < 7 at t=0.5, got ${halfIn.zoom}`);

  const zoomOut: CameraKey[] = [
    { t: 0, center: [56.4, 26.4], zoom: 5.2 },
    { t: 1, center: [98.08355, 31.1540786], zoom: 2.01733745 },
  ];
  const earlyOut = cameraAt(zoomOut, 0.2, 'linear', { path: 'fly', width: 640, height: 360 });
  const panFraction = (earlyOut.center[0] - 56.4) / (98.08355 - 56.4);
  // During zoom-out, pan stays slow while zoomed in so the origin stays framed while pulling back.
  assert.ok(panFraction < 0.1, `expected panFraction < 0.1 at t=0.2, got ${panFraction}`);

  // Pure zoom in place falls back to linear zoom without NaN.
  const pureZoom: CameraKey[] = [
    { t: 0, center: [139.7671, 35.6812], zoom: 10 },
    { t: 1, center: [139.7671, 35.6812], zoom: 15 },
  ];
  assert.equal(cameraAt(pureZoom, 0.5, 'linear', { path: 'fly' }).zoom, 12.5);
});

test('sliceLine returns the first fraction of the line by length', () => {
  const line: [number, number][] = [[0, 0], [1, 0], [1, 1]];
  assert.deepEqual(sliceLine(line, 0), [[0, 0], [0, 0]]);
  assert.deepEqual(sliceLine(line, 1), line);
  const half = sliceLine(line, 0.5);
  assert.deepEqual(half[half.length - 1], [1, 0]);
  const q = sliceLine(line, 0.25);
  assert.ok(Math.abs(q[q.length - 1]![0] - 0.5) < 1e-9);
});

test('locate maps a global time to a shot and local progress', () => {
  const shots = [{ duration: 2 }, { duration: 3 }];
  assert.deepEqual(locate(shots, 0), { index: 0, t: 0, sec: 0 });
  assert.deepEqual(locate(shots, 1), { index: 0, t: 0.5, sec: 1 });
  assert.deepEqual(locate(shots, 2.5), { index: 1, t: 0.5 / 3, sec: 0.5 });
  assert.equal(locate(shots, 99).index, 1);
});

test('fadeAlpha fades in and out over the window', () => {
  assert.equal(fadeAlpha([0.2, 0.8], 0.1, 0.1), 0);
  assert.equal(fadeAlpha([0.2, 0.8], 0.5, 0.1), 1);
  assert.ok(Math.abs(fadeAlpha([0.2, 0.8], 0.25, 0.1) - 0.5) < 1e-9);
  assert.equal(fadeAlpha(undefined, 0.5, 0.1), 1);
});

test('countValue counts up and keeps the given decimals', () => {
  assert.equal(countValue({ value: 2500, countUp: [0, 0.5], countEase: 'linear' }, 0.25), '1,250');
  assert.ok(Number(countValue({ value: 2500, countUp: [0, 0.5] }, 0.25).replace(',', '')) > 1250);
  assert.equal(countValue({ value: 2500, countUp: [0.2, 0.5] }, 0.1), '0');
  assert.equal(countValue({ value: 2500, countUp: [0, 0.5] }, 0.9), '2,500');
  assert.equal(countValue({ value: 2.8, decimals: 1 }, 0.1), '2.8');
  assert.equal(countValue({ value: '40〜50' }, 0.1), '40〜50');
  assert.equal(countValue({ value: 1969, from: 1950, grouping: false, countUp: [0, 1], countEase: 'linear' }, 0.5), '1960');
  assert.equal(countValue({ value: 1969, grouping: false }, 0), '1969');
});

test('wrapSubtitle keeps short lines and splits long ones at punctuation near the middle', () => {
  assert.equal(wrapSubtitle('短い字幕', 26), '短い字幕');
  assert.equal(wrapSubtitle('改行は\nそのまま', 4), '改行は\nそのまま');
  const t = 'ここから流れ出す土砂は、平均して毎年ダンプ約3万台分になるんだ。';
  const w = wrapSubtitle(t, 20);
  assert.equal(w.replace('\n', ''), t);
  assert.equal(w.split('\n').length, 2);
  assert.ok(w.split('\n')[0]!.endsWith('、'));
  const n = 'あいうえおかきくけこさしすせそたちつてと';
  assert.equal(wrapSubtitle(n, 12).split('\n')[0]!.length, 10);
});

test('layoutLines puts lines one after another and stretches the shot to fit', () => {
  const r = layoutLines([1.0, 2.0], { duration: 2, padStart: 0.5, pause: 0.25, padEnd: 0.5 });
  assert.equal(r.duration, 4.25);
  assert.deepEqual(r.starts, [0.5, 1.75]);
  assert.ok(Math.abs(r.windows[0]![0] - 0.5 / 4.25) < 1e-9);
  assert.ok(Math.abs(r.windows[0]![1] - 1.75 / 4.25) < 1e-9);
  assert.equal(r.windows[1]![1], 1);
  assert.equal(layoutLines([1.0], { duration: 6, padStart: 0.5, pause: 0.25, padEnd: 0.5 }).duration, 6);
  assert.equal(layoutLines([], { duration: 3 }).duration, 3);
});

test('estimateSeconds approximates speech time from characters', () => {
  assert.equal(estimateSeconds('あいうえお、かきくけこ。', 5), 2);
});

test('writeWav and parseWav round-trip 16-bit mono PCM', () => {
  const f = path.join(os.tmpdir(), `flyover-${process.pid}.wav`);
  const s = new Int16Array([0, 1000, -1000, 32767, -32768]);
  writeWav(f, s, 24000);
  const w = parseWav(fs.readFileSync(f));
  fs.rmSync(f);
  assert.equal(w.rate, 24000);
  assert.deepEqual([...w.samples], [...s]);
  assert.ok(Math.abs(w.seconds - 5 / 24000) < 1e-12);
});

test('phase gives seconds since the overlay appeared and until it leaves', () => {
  assert.deepEqual(phase([0.2, 0.8], 0.5, 10), { since: 3, until: 3, on: true });
  assert.equal(phase([0.2, 0.8], 0.1, 10).on, false);
  assert.deepEqual(phase(undefined, 0.5, 4), { since: 2, until: Infinity, on: true });
  assert.equal(phase([0.2, 1], 0.9, 10).until, Infinity);
});

test('easeOutBack overshoots then settles at 1', () => {
  assert.equal(easeOutBack(0), 0);
  assert.ok(Math.abs(easeOutBack(1) - 1) < 1e-12);
  assert.ok(Math.max(...[0.5, 0.6, 0.7, 0.8].map(easeOutBack)) > 1);
});

test('typeCount reveals characters at a steady rate', () => {
  assert.equal(typeCount('あいうえお', 0, 10), 0);
  assert.equal(typeCount('あいうえお', 0.25, 10), 2);
  assert.equal(typeCount('あいうえお', 9, 10), 5);
});

test('chartGeometry maps points into the plot box and measures the path', () => {
  const g = chartGeometry(
    [['2021-01', 100], ['2021-07', 200], ['2022-01', 150]],
    { w: 200, h: 100, pad: [10, 10, 10, 10], ymin: 100, ymax: 200 },
  );
  assert.deepEqual(g.pts[0], [10, 90]);
  assert.deepEqual(g.pts[1]!.map(Math.round), [Math.round(10 + 180 * (181 / 365)), 10]);
  assert.ok(Math.abs(g.pts[2]![0] - 190) < 1e-9);
  assert.ok(g.length > 180);
  assert.ok(Math.abs(g.cum[2]! - g.length) < 1e-9);
});

test('odometerColumns rolls the ones continuously and carries into higher digits only at the rollover', () => {
  // 1234.5: ones half way from 4 to 5, tens still on 3
  assert.deepEqual(odometerColumns(1234.5, 4), [1, 2, 3, 4.5]);
  // 1299.5: the 9s are rolling over, so tens and hundreds move half a step too
  assert.deepEqual(odometerColumns(1299.5, 4), [1, 2.5, 9.5, 9.5]);
  // whole numbers sit exactly on their digits; columns are padded to the final width
  assert.deepEqual(odometerColumns(7, 3), [0, 0, 7]);
  assert.deepEqual(odometerColumns(19756, 5), [1, 9, 7, 5, 6]);
});

test('counterNumber returns the raw counting value for rolling digits', () => {
  assert.equal(counterNumber({ value: 2000, countUp: [0, 1], countEase: 'linear' }, 0.5), 1000);
  assert.equal(counterNumber({ value: 2000 }, 0.1), 2000);
  assert.equal(counterNumber({ value: '19,756' }, 0.1), null);
});

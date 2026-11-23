import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
  blankFrames,
  evaluatePerf,
  parseFrameCount,
  parseSignalStats,
  readBaseline,
  updateBaseline,
  type PerfBaseline,
} from './support/perf.js';

test('parseFrameCount reads the last progress line of the renderer', () => {
  assert.equal(parseFrameCount('credits: x\n\r30/180 frames, 2 s\r180/180 frames, 11 s\nvideo: out.mp4\n'), 180);
  assert.equal(parseFrameCount('nothing'), null);
});

test('evaluatePerf passes without a baseline and within the allowed factor', () => {
  const base: PerfBaseline = { base: { frames: 100, msPerFrame: 100 } };
  assert.equal(evaluatePerf('new-case', { frames: 10, msPerFrame: 9999 }, base).ok, true);
  assert.equal(evaluatePerf('base', { frames: 100, msPerFrame: 100 }, base).ok, true);
  assert.equal(evaluatePerf('base', { frames: 100, msPerFrame: 299 }, base).ok, true);
});

test('evaluatePerf fails past the factor and names the case, the numbers and how to update', () => {
  const base: PerfBaseline = { base: { frames: 100, msPerFrame: 100 } };
  const r = evaluatePerf('base', { frames: 100, msPerFrame: 301 }, base);
  assert.equal(r.ok, false);
  assert.match(r.message, /base/);
  assert.match(r.message, /301/);
  assert.match(r.message, /100/);
  assert.match(r.message, /GVF_PERF_UPDATE=1/);
});

test('evaluatePerf ignores noise on very fast cases (absolute floor) and honours a custom factor', () => {
  const base: PerfBaseline = { quick: { frames: 10, msPerFrame: 5 } };
  assert.equal(evaluatePerf('quick', { frames: 10, msPerFrame: 40 }, base).ok, true, '8x of 5 ms is still only 35 ms more');
  assert.equal(evaluatePerf('quick', { frames: 10, msPerFrame: 400 }, base).ok, false);
  const slow: PerfBaseline = { c: { frames: 10, msPerFrame: 100 } };
  assert.equal(evaluatePerf('c', { frames: 10, msPerFrame: 160 }, slow, { factor: 1.5 }).ok, false);
});

test('evaluatePerf can be switched off with GVF_PERF=off', () => {
  const base: PerfBaseline = { c: { frames: 10, msPerFrame: 1 } };
  assert.equal(evaluatePerf('c', { frames: 10, msPerFrame: 10_000 }, base, { off: true }).ok, true);
});

test('readBaseline tolerates a missing file; updateBaseline merges and keeps keys sorted', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gvf-perf-'));
  const file = path.join(dir, 'perf-baseline.json');
  assert.deepEqual(readBaseline(file), {});
  updateBaseline(file, 'b', { frames: 2, msPerFrame: 20.04 });
  updateBaseline(file, 'a', { frames: 1, msPerFrame: 10 });
  updateBaseline(file, 'b', { frames: 3, msPerFrame: 30 });
  assert.deepEqual(Object.keys(readBaseline(file)), ['a', 'b']);
  assert.deepEqual(readBaseline(file).b, { frames: 3, msPerFrame: 30 });
  assert.ok(fs.readFileSync(file, 'utf8').endsWith('\n'));
});

const stats = (frames: [number, number, number][]) =>
  frames.map(([avg, min, max], i) => `frame:${i}    pts:${i}    pts_time:${i}\nlavfi.signalstats.YMIN=${min}\nlavfi.signalstats.YAVG=${avg}\nlavfi.signalstats.YMAX=${max}\n`).join('');

test('parseSignalStats reads per-frame luma min, mean and max', () => {
  const frames = parseSignalStats(stats([[100.5, 10, 200], [50, 16, 90]]));
  assert.deepEqual(frames, [{ yavg: 100.5, ymin: 10, ymax: 200 }, { yavg: 50, ymin: 16, ymax: 90 }]);
  assert.deepEqual(parseSignalStats(''), []);
});

test('blankFrames flags black, white and flat frames only', () => {
  const frames = parseSignalStats(stats([[100, 10, 200], [16, 16, 16], [235, 235, 235], [120, 100, 102], [60, 20, 250]]));
  assert.deepEqual(blankFrames(frames), [1, 2, 3]);
  assert.deepEqual(blankFrames([]), [], 'no frames is the caller\'s problem, not a blank frame');
});

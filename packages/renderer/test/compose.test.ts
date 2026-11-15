import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { describe, it } from 'node:test';
import { wipeSequenceFilter, wipeAt, wipeExpression, wipeFilter } from '../src/compose.js';

describe('before/after slider', () => {
  const keys: [number, number][] = [[1, 0], [2, 0.5], [4, 0.5], [5, 1]];

  it('moves the divider linearly between keys and holds the ends', () => {
    assert.equal(wipeAt(keys, 0), 0);
    assert.equal(wipeAt(keys, 1.5), 0.25);
    assert.equal(wipeAt(keys, 3), 0.5);
    assert.equal(wipeAt(keys, 4.5), 0.75);
    assert.equal(wipeAt(keys, 9), 1);
    assert.equal(wipeAt([], 3), 0);
  });

  it('writes the same function as an ffmpeg expression', () => {
    const expr = wipeExpression(keys);
    for (const t of [0, 1.5, 3, 4.5, 9]) {
      const js = expr
        .replaceAll('if(', 'iff(')
        .replaceAll('lt(', 'ltf(')
        .replaceAll('T', String(t));
      const value = new Function('iff', 'ltf', `return ${js};`)((c: number, a: number, b: number) => (c ? a : b), (a: number, b: number) => (a < b ? 1 : 0));
      assert.ok(Math.abs(value - wipeAt(keys, t)) < 1e-9, `t=${t}: ${value}`);
    }
  });

  it('composes two clips so the left shows the first and the right the second', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wipe-'));
    const run = (args: string[]) => {
      const r = spawnSync('ffmpeg', ['-v', 'error', '-y', ...args], { encoding: 'utf8' });
      assert.equal(r.status, 0, r.stderr);
    };
    run(['-f', 'lavfi', '-i', 'color=c=black:s=64x16:d=1:r=10', path.join(dir, 'a.mp4')]);
    run(['-f', 'lavfi', '-i', 'color=c=white:s=64x16:d=1:r=10', path.join(dir, 'b.mp4')]);
    run(['-i', path.join(dir, 'a.mp4'), '-i', path.join(dir, 'b.mp4'), '-filter_complex', wipeFilter([[0, 0.5]], 2), '-map', '[v]',
      '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'gray', path.join(dir, 'out.gray')]);
    const pixels = fs.readFileSync(path.join(dir, 'out.gray'));
    const row = pixels.subarray(8 * 64, 9 * 64);
    assert.ok(row[4]! < 40, 'left quarter is the first clip');
    assert.ok(row[60]! > 215, 'right quarter is the second clip');
    run(['-f', 'lavfi', '-i', 'color=c=gray:s=64x16:d=1:r=10', path.join(dir, 'i.mp4')]);
    run(['-i', path.join(dir, 'i.mp4'), '-i', path.join(dir, 'i.mp4'), '-i', path.join(dir, 'a.mp4'), '-i', path.join(dir, 'b.mp4'), '-filter_complex', wipeSequenceFilter([[[0, 1]], [[0, 0]]], 2),
      '-map', '[v]', path.join(dir, 'joined.mp4')]);
    const probe = spawnSync('ffprobe', ['-v', 'error', '-count_frames', '-select_streams', 'v', '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', path.join(dir, 'joined.mp4')], { encoding: 'utf8' });
    assert.equal(probe.stdout.trim(), '20', 'the first slider (10 frames) is followed by the second (10 frames)');
    fs.rmSync(dir, { recursive: true, force: true });
  });
});

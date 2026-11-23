import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loudnormSecondPass, mp4EncodeArgs, parseLoudnormJson, stillsSheetArgs } from '../src/render.js';

test('mp4EncodeArgs: h264 high profile, yuv420p, keyframe every 2 s, faststart, output last', () => {
  const a = mp4EncodeArgs(30, 'out.mp4');
  assert.equal(a.at(-1), 'out.mp4');
  const val = (k: string) => a[a.indexOf(k) + 1];
  assert.equal(val('-c:v'), 'libx264');
  assert.equal(val('-pix_fmt'), 'yuv420p');
  assert.equal(val('-crf'), '18');
  assert.equal(val('-profile:v'), 'high');
  assert.equal(val('-g'), '60');
  assert.equal(val('-movflags'), '+faststart');
  assert.equal(mp4EncodeArgs(24, 'x.mp4')[mp4EncodeArgs(24, 'x.mp4').indexOf('-g') + 1], '48');
});

test('stillsSheetArgs tiles up to 4 columns and as many rows as needed', () => {
  const vf = (n: number) => stillsSheetArgs('/f', 'jpg', '/s.jpg', n)[stillsSheetArgs('/f', 'jpg', '/s.jpg', n).indexOf('-vf') + 1];
  assert.equal(vf(2), 'scale=480:-1,tile=2x1');
  assert.equal(vf(4), 'scale=480:-1,tile=4x1');
  assert.equal(vf(9), 'scale=480:-1,tile=4x3');
  assert.ok(stillsSheetArgs('/f', 'png', '/s.jpg', 3).includes('/f/%05d.png'));
  assert.equal(stillsSheetArgs('/f', 'jpg', '/s.jpg', 3).at(-1), '/s.jpg');
});

test('parseLoudnormJson takes the last JSON block of ffmpeg stderr', () => {
  const stderr = 'noise {not json}\n[Parsed_loudnorm_0]\n{\n "input_i": "-20.1",\n "input_tp": "-3.0",\n "input_lra": "5.2",\n "input_thresh": "-30.5",\n "target_offset": "0.4"\n}\n';
  assert.equal(parseLoudnormJson(stderr).input_i, '-20.1');
});

test('loudnormSecondPass embeds the measured values and is linear', () => {
  const s = loudnormSecondPass({ input_i: '-20.1', input_tp: '-3.0', input_lra: '5.2', input_thresh: '-30.5', target_offset: '0.4' });
  assert.equal(
    s,
    'loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=-20.1:measured_TP=-3.0:measured_LRA=5.2:measured_thresh=-30.5:offset=0.4:linear=true',
  );
});

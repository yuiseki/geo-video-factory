import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loudnormSecondPass, mp4EncodeArgs, parseLoudnormJson, stillsSheetArgs, transparentEncodeArgs } from '../src/ffmpeg-args.js';

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

import { downscaleFilter, parseSupersample, supersampledSize } from '../src/ffmpeg-args.js';

test('parseSupersample: default 1, integers 1 to 4, anything else is an error', () => {
  assert.equal(parseSupersample(undefined), 1);
  assert.equal(parseSupersample('1'), 1);
  assert.equal(parseSupersample('2'), 2);
  assert.equal(parseSupersample('4'), 4);
  for (const bad of ['0', '5', '1.5', '-2', 'x', '']) assert.throws(() => parseSupersample(bad), /--supersample must be an integer from 1 to 4/, bad);
});

test('supersampledSize multiplies both sides', () => {
  assert.deepEqual(supersampledSize([1280, 720], 1), [1280, 720]);
  assert.deepEqual(supersampledSize([1280, 720], 2), [2560, 1440]);
});

test('downscaleFilter is absent at 1x and a lanczos scale back to the output size otherwise', () => {
  assert.equal(downscaleFilter([1280, 720], 1), null);
  assert.equal(downscaleFilter([1280, 720], 2), 'scale=1280:720:flags=lanczos');
});

test('mp4EncodeArgs puts the downscale filter before the codec options when given', () => {
  const a = mp4EncodeArgs(30, 'o.mp4', 'scale=640:360:flags=lanczos');
  assert.equal(a[a.indexOf('-vf') + 1], 'scale=640:360:flags=lanczos');
  assert.ok(a.indexOf('-vf') < a.indexOf('-c:v'));
  assert.equal(a.at(-1), 'o.mp4');
  assert.equal(mp4EncodeArgs(30, 'o.mp4').includes('-vf'), false);
});

test('transparentEncodeArgs: qtrle with alpha, with the same optional downscale', () => {
  assert.deepEqual(transparentEncodeArgs('o.mov'), ['-c:v', 'qtrle', '-pix_fmt', 'argb', 'o.mov']);
  assert.deepEqual(transparentEncodeArgs('o.mov', 'scale=1:1'), ['-vf', 'scale=1:1', '-c:v', 'qtrle', '-pix_fmt', 'argb', 'o.mov']);
});

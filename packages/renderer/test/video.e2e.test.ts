import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

test('E2E: renderer writes a playable MP4 to dist/test/video', { timeout: 120_000 }, () => {
  const output = path.resolve('dist/test/video');
  fs.rmSync(output, { recursive: true, force: true });
  const renderEnv = { ...process.env };
  // Keep the child CLI's process coverage separate from this test process's unit coverage.
  delete renderEnv.NODE_V8_COVERAGE;

  const render = spawnSync(
    process.execPath,
    [
      'dist/src/render.js',
      'test/fixtures/e2e-video.json',
      '--project',
      'test/fixtures',
      '--out',
      output,
      '--no-voice',
      '--raw-audio',
    ],
    { encoding: 'utf8', timeout: 110_000, env: renderEnv },
  );
  assert.equal(render.status, 0, `${render.stdout}\n${render.stderr}`);

  const video = path.join(output, 'video.mp4');
  assert.ok(fs.statSync(video).size > 1_000, 'rendered MP4 should not be empty');
  const probe = spawnSync(
    'ffprobe',
    ['-v', 'error', '-show_entries', 'stream=codec_type,width,height:format=duration', '-of', 'json', video],
    { encoding: 'utf8' },
  );
  assert.equal(probe.status, 0, probe.stderr);
  const metadata = JSON.parse(probe.stdout) as {
    streams: { codec_type: string; width?: number; height?: number }[];
    format: { duration: string };
  };
  const stream = metadata.streams.find(({ codec_type }) => codec_type === 'video');
  assert.deepEqual([stream?.width, stream?.height], [320, 180]);
  assert.ok(Number(metadata.format.duration) >= 0.5);
});

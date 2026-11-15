import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

interface VideoCase {
  name: string;
  fixture: string;
  minimumDuration: number;
}

const cases: VideoCase[] = [
  { name: 'base', fixture: 'base-video.json', minimumDuration: 0.5 },
  { name: 'earth-tokyo-station', fixture: 'earth-tokyo-station.json', minimumDuration: 13.5 },
  { name: 'terrain-mt-fuji', fixture: 'terrain-mt-fuji.json', minimumDuration: 9.5 },
];

function probeVideo(video: string): { width: number; height: number; duration: number } {
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
  assert.ok(stream?.width && stream.height, `${video} must contain a video stream`);
  return { width: stream.width, height: stream.height, duration: Number(metadata.format.duration) };
}

test('E2E: renderer writes base, earth flight and terrain orbit MP4s', { timeout: 240_000 }, () => {
  const output = path.resolve('dist/test/video');
  const work = path.join(output, '.work');
  fs.rmSync(output, { recursive: true, force: true });
  fs.mkdirSync(work, { recursive: true });
  const renderEnv = { ...process.env };
  // Keep the child CLI's process coverage separate from this test process's unit coverage.
  delete renderEnv.NODE_V8_COVERAGE;

  for (const item of cases) {
    const renderOutput = path.join(work, item.name);
    const render = spawnSync(
      process.execPath,
      [
        'dist/src/render.js',
        path.join('test/fixtures', item.fixture),
        '--project',
        'test/fixtures',
        '--out',
        renderOutput,
        '--no-voice',
        '--raw-audio',
      ],
      { encoding: 'utf8', timeout: 220_000, env: renderEnv },
    );
    assert.equal(render.status, 0, `${item.name}\n${render.stdout}\n${render.stderr}`);

    const rendered = path.join(renderOutput, `${item.name}.mp4`);
    const video = path.join(output, `${item.name}.mp4`);
    fs.copyFileSync(rendered, video);
    assert.ok(fs.statSync(video).size > 1_000, `${item.name}.mp4 should not be empty`);
    const metadata = probeVideo(video);
    assert.deepEqual([metadata.width, metadata.height], [640, 360]);
    assert.ok(metadata.duration >= item.minimumDuration, `${item.name}.mp4 is too short`);
  }
});

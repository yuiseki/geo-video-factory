import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fitLngLatBounds, projectLngLat } from '../src/map-viewport.js';

interface VideoCase {
  name: string;
  fixture: string;
  minimumDuration: number;
}

const cases: VideoCase[] = [
  { name: 'base', fixture: 'base-video.json', minimumDuration: 0.5 },
  { name: 'earth-tokyo-station', fixture: 'earth-tokyo-station.json', minimumDuration: 20.4 },
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

test('long-distance fixture separates moves from two-second geographic holds', () => {
  const fixture = JSON.parse(fs.readFileSync('test/fixtures/earth-tokyo-station.json', 'utf8')) as {
    shots: { duration: number; from: { center: number[]; zoom: number; pitch: number; bearing: number }; to: { center: number[]; zoom: number; pitch: number; bearing: number } }[];
  };
  assert.deepEqual(fixture.shots.map(({ duration }) => duration), [1.5, 2, 5, 2, 5, 2, 3]);
  for (const shot of fixture.shots) {
    assert.equal(shot.from.pitch, 0);
    assert.equal(shot.to.pitch, 0);
  }
  for (let index = 1; index < fixture.shots.length; index++) {
    assert.deepEqual(fixture.shots[index]!.from, fixture.shots[index - 1]!.to, `camera discontinuity at shot ${index}`);
  }
  for (const index of [1, 3, 5]) assert.deepEqual(fixture.shots[index]!.from, fixture.shots[index]!.to);

  const wideCamera = fixture.shots[3]!.from;
  const expected = fitLngLatBounds([[56.4, 26.4], [139.7671, 35.6812]], { width: 640, height: 360, padding: 80 });
  assert.ok(Math.abs(wideCamera.center[0]! - expected.center[0]) < 1e-4);
  assert.ok(Math.abs(wideCamera.center[1]! - expected.center[1]) < 1e-4);
  assert.ok(Math.abs(wideCamera.zoom - expected.zoom) < 1e-4);
  for (const point of [[56.4, 26.4], [139.7671, 35.6812]] as [number, number][]) {
    const screen = projectLngLat(point, { center: wideCamera.center as [number, number], zoom: wideCamera.zoom }, { width: 640, height: 360, padding: 80 });
    assert.ok(screen.x >= 79.999 && screen.x <= 560.001);
    assert.ok(screen.y >= 79.999 && screen.y <= 280.001);
  }
});

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

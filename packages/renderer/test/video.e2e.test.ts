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
  width?: number;
  height?: number;
}

const cases: VideoCase[] = [
  { name: 'base', fixture: 'base-video.json', minimumDuration: 0.5 },
  { name: 'earth-tokyo-station', fixture: 'earth-tokyo-station.json', minimumDuration: 20.4 },
  { name: 'terrain-mt-fuji', fixture: 'terrain-mt-fuji.json', minimumDuration: 19.9 },
  { name: 'terrain-mt-omuroyama', fixture: 'terrain-mt-omuroyama.json', minimumDuration: 47.9, width: 1280, height: 720 },
  { name: 'choropleth-3d-tokyo23', fixture: 'choropleth-3d-tokyo23.json', minimumDuration: 5.9 },
  { name: 'choropleth-3d-japan-pref', fixture: 'choropleth-3d-japan-pref.json', minimumDuration: 5.9 },
  { name: 'choropleth-3d-japan-pref-to-tokyo23', fixture: 'choropleth-3d-japan-pref-to-tokyo23.json', minimumDuration: 14.4 },
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

test('Fuji E2E makes one wide orbit, then zooms in through a second orbit', () => {
  const fixture = JSON.parse(fs.readFileSync('test/fixtures/terrain-mt-fuji.json', 'utf8')) as {
    shots: {
      duration: number;
      ease?: string;
      from?: { center: number[]; zoom: number; pitch: number; bearing: number };
      to?: { center: number[]; zoom: number; pitch: number; bearing: number };
      keys: { t: number; center: number[]; zoom: number; pitch: number; bearing: number }[];
    }[];
  };
  assert.equal(fixture.shots.length, 2, 'wide orbit followed by zoom-in orbit');
  assert.deepEqual(fixture.shots.map(({ duration }) => duration), [8, 12]);
  const [wide, zoomIn] = fixture.shots as [typeof fixture.shots[number], typeof fixture.shots[number]];
  for (const shot of [wide, zoomIn]) {
    assert.equal(shot.ease, 'linear', 'continuous orbit uses linear timing');
    assert.deepEqual(shot.keys.map(({ t }) => t), [0, 0.25, 0.5, 0.75, 1], 'orbit has no stationary intervals');
  }
  assert.ok(wide.keys.every(({ zoom }) => zoom < 9), 'first orbit keeps the full mountain in a wide view');
  assert.ok(zoomIn.keys.at(-1)!.zoom > zoomIn.keys[0]!.zoom + 2, 'second orbit zooms in substantially');
  assert.ok(zoomIn.keys.every((key, i) => i === 0 || key.zoom > zoomIn.keys[i - 1]!.zoom), 'second orbit zooms in continuously');
  assert.ok(zoomIn.keys.slice(1).every((key, i) => Math.abs((key.zoom - zoomIn.keys[i]!.zoom) - 0.65) < 1e-9), 'zoom-in rate stays even across the orbit');
  const wideEnd = wide.keys.at(-1)!;
  const zoomInStart = zoomIn.keys[0]!;
  assert.deepEqual(
    { center: zoomInStart.center, zoom: zoomInStart.zoom, pitch: zoomInStart.pitch, bearing: zoomInStart.bearing },
    { center: wideEnd.center, zoom: wideEnd.zoom, pitch: wideEnd.pitch, bearing: wideEnd.bearing },
    'zoom-in orbit starts at the end of the wide orbit',
  );
  for (const shot of [wide, zoomIn]) {
    const turns = shot.keys.slice(1).reduce((total, key, i) => {
      const previous = shot.keys[i]!;
      return total + (((key.bearing - previous.bearing + 540) % 360) - 180);
    }, 0);
    assert.ok(Math.abs(Math.abs(turns) - 360) < 2, `orbit should rotate once, got ${turns} degrees`);
    for (const key of shot.keys) assert.deepEqual(key.center, [138.7274, 35.3606]);
  }
});

test('Omuroyama E2E loops seamlessly across four seasons in four slow linear orbits (1 orbit per season)', () => {
  const fixture = JSON.parse(fs.readFileSync('test/fixtures/terrain-mt-omuroyama.json', 'utf8')) as {
    shots: {
      duration: number;
      ease?: string;
      keys: { t: number; center: number[]; zoom: number; pitch: number; bearing: number }[];
      overlays: { type: string; src?: string }[];
    }[];
  };
  assert.equal(fixture.shots.length, 1);
  const shot = fixture.shots[0]!;
  assert.equal(shot.duration, 48);
  assert.equal(shot.ease, 'linear');
  assert.equal(shot.keys[0]!.t, 0);
  assert.equal(shot.keys.at(-1)!.t, 1);
  for (const key of shot.keys) assert.deepEqual(key.center, [139.0947222, 34.9030556]);
  const turns = shot.keys.slice(1).reduce((total, key, i) => {
    const previous = shot.keys[i]!;
    return total + (((key.bearing - previous.bearing + 540) % 360) - 180);
  }, 0);
  assert.equal(turns, 1440);
  assert.equal(shot.keys.at(-1)!.zoom, shot.keys[0]!.zoom);
  assert.equal(shot.keys.at(-1)!.pitch, shot.keys[0]!.pitch);
  const seasonImages = shot.overlays.filter((o) => o.type === 'image').map((o) => o.src);
  assert.deepEqual(seasonImages, [
    'omuro-seasons/summer.jpg',
    'omuro-seasons/autumn.jpg',
    'omuro-seasons/winter_burn.jpg',
    'omuro-seasons/spring.jpg',
  ]);
});

test('Tokyo 23 wards 3D choropleth E2E tilts subtly while extrusions rise with a legend', () => {
  const fixture = JSON.parse(fs.readFileSync('test/fixtures/choropleth-3d-tokyo23.json', 'utf8')) as {
    shots: {
      duration: number;
      ease?: string;
      from: { center: number[]; zoom: number; pitch: number; bearing: number };
      to: { center: number[]; zoom: number; pitch: number; bearing: number };
      overlays: { type: string; src?: string; extrude?: boolean; property?: string; labelProperty?: string; rise?: number[]; legend?: unknown }[];
    }[];
  };
  assert.equal(fixture.shots.length, 1);
  const shot = fixture.shots[0]!;
  assert.equal(shot.duration, 6);
  assert.ok(shot.from.pitch >= 40 && shot.to.pitch > shot.from.pitch);
  assert.ok(Math.abs(shot.to.bearing - shot.from.bearing) <= 20, 'keeps north-up orientation readable');
  const choropleth = shot.overlays.find((o) => o.type === 'choropleth');
  assert.ok(choropleth);
  assert.equal(choropleth.src, 'tokyo23-population.geojson');
  assert.equal(choropleth.property, 'population');
  assert.equal(choropleth.labelProperty, 'name');
  assert.equal(choropleth.extrude, true);
  assert.ok(choropleth.rise && choropleth.rise.length === 2);
  assert.ok(choropleth.legend, 'Tokyo 23 wards choropleth should include a legend');
});

test('Japan 47 prefectures 3D choropleth E2E tilts subtly while extrusions rise with labels and legend', () => {
  const fixture = JSON.parse(fs.readFileSync('test/fixtures/choropleth-3d-japan-pref.json', 'utf8')) as {
    shots: {
      duration: number;
      from: { pitch: number; bearing: number };
      to: { pitch: number; bearing: number };
      overlays: { type: string; src?: string; extrude?: boolean; property?: string; labelProperty?: string; rise?: number[]; legend?: unknown }[];
    }[];
  };
  assert.equal(fixture.shots.length, 1);
  const shot = fixture.shots[0]!;
  assert.equal(shot.duration, 6);
  assert.ok(shot.from.pitch >= 40 && shot.to.pitch > shot.from.pitch);
  const choropleth = shot.overlays.find((o) => o.type === 'choropleth');
  assert.ok(choropleth);
  assert.equal(choropleth.src, 'japan-pref-population.geojson');
  assert.equal(choropleth.property, 'population');
  assert.equal(choropleth.labelProperty, 'name');
  assert.equal(choropleth.extrude, true);
  assert.ok(choropleth.rise && choropleth.rise.length === 2);
  assert.ok(choropleth.legend);
});

test('Japan 47 prefectures to Tokyo 23 wards 3D choropleth E2E centers Tokyo and dims others before zooming', () => {
  const fixture = JSON.parse(fs.readFileSync('test/fixtures/choropleth-3d-japan-pref-to-tokyo23.json', 'utf8')) as {
    shots: {
      duration: number;
      from: { center: number[]; zoom: number; pitch: number; bearing: number };
      to: { center: number[]; zoom: number; pitch: number; bearing: number };
      overlays: { type: string; src?: string; focus?: { values: string[]; dimOpacity?: number } }[];
    }[];
  };
  assert.equal(fixture.shots.length, 4);
  assert.deepEqual(fixture.shots.map(({ duration }) => duration), [4.5, 2.5, 3.0, 4.5]);
  for (let i = 1; i < fixture.shots.length; i++) {
    assert.deepEqual(fixture.shots[i]!.from, fixture.shots[i - 1]!.to, `camera discontinuity at shot ${i}`);
  }
  const panShot = fixture.shots[1]!;
  assert.deepEqual(panShot.to.center, [139.742, 35.669]);
  assert.equal(panShot.overlays[0]?.focus?.values[0], '東京都');
  const zoomShot = fixture.shots[2]!;
  assert.deepEqual(zoomShot.from.center, [139.742, 35.669]);
  assert.deepEqual(zoomShot.to.center, [139.742, 35.669]);
  assert.ok(zoomShot.to.zoom > zoomShot.from.zoom + 4);
});

test('E2E: renderer writes selected video MP4s', { timeout: 600_000 }, () => {
  const output = path.resolve('dist/test/video');
  const work = path.join(output, '.work');
  const target = process.env.VIDEO_TARGET?.trim();
  const selectedCases = target ? cases.filter(({ name }) => name === target) : cases;
  assert.ok(selectedCases.length, `unknown VIDEO_TARGET "${target}"; choose one of: ${cases.map(({ name }) => name).join(', ')}`);
  if (!target) fs.rmSync(output, { recursive: true, force: true });
  fs.mkdirSync(work, { recursive: true });
  const renderEnv = { ...process.env };
  // Keep the child CLI's process coverage separate from this test process's unit coverage.
  delete renderEnv.NODE_V8_COVERAGE;

  for (const item of selectedCases) {
    const renderOutput = path.join(work, item.name);
    fs.rmSync(renderOutput, { recursive: true, force: true });
    fs.rmSync(path.join(work, `${item.name}.log`), { force: true });
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
      { encoding: 'utf8', timeout: 420_000, env: renderEnv },
    );
    assert.equal(render.status, 0, `${item.name}\n${render.stdout}\n${render.stderr}`);

    const rendered = path.join(renderOutput, `${item.name}.mp4`);
    const video = path.join(output, `${item.name}.mp4`);
    fs.copyFileSync(rendered, video);
    assert.ok(fs.statSync(video).size > 1_000, `${item.name}.mp4 should not be empty`);
    const metadata = probeVideo(video);
    assert.deepEqual([metadata.width, metadata.height], [item.width ?? 640, item.height ?? 360]);
    assert.ok(metadata.duration >= item.minimumDuration, `${item.name}.mp4 is too short`);
  }
});

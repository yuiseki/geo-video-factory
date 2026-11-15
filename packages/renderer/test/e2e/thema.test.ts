import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const videoName = 'buildings-asakusa';
const fixturePath = path.join('test/fixtures', `${videoName}.json`);

test(`${videoName} E2E case and output use the buildings- prefix`, () => {
  assert.match(videoName, /^buildings-/);
});

test(`${videoName} E2E uses a complete, repository-local PLATEAU fixture`, () => {
  const spec = JSON.parse(fs.readFileSync(fixturePath, 'utf8')) as {
    plateauBuildings?: { manifest: string };
  };
  assert.ok(spec.plateauBuildings?.manifest, 'PLATEAU manifest is required');
  const manifestPath = path.join('test/fixtures', spec.plateauBuildings.manifest);
  assert.ok(!manifestPath.split(path.sep).includes('tmp'), 'fixture must not read from tmp/');
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8')) as {
    format: string;
    tiles: { glb: string; ids?: string[] }[];
  };
  assert.equal(manifest.format, 'geo-video-factory.plateau-3d/1');
  assert.ok(manifest.tiles.length > 0, 'PLATEAU fixture must include model tiles');
  for (const tile of manifest.tiles) {
    assert.ok(fs.existsSync(path.resolve(path.dirname(manifestPath), tile.glb)), `missing committed GLB ${tile.glb}`);
    assert.ok(tile.ids?.length, `missing building IDs for ${tile.glb}`);
  }
});

test(`${videoName} E2E: renderer writes selected PLATEAU MP4`, { timeout: 600_000 }, (t) => {
  const target = process.env.VIDEO_TARGET?.trim();
  if (target && target !== videoName) {
    t.skip(`VIDEO_TARGET=${target}`);
    return;
  }

  const output = path.resolve('dist/test/video');
  const work = path.join(output, '.work');
  fs.mkdirSync(output, { recursive: true });
  fs.mkdirSync(work, { recursive: true });

  const renderOutput = path.join(work, videoName);
  fs.rmSync(renderOutput, { recursive: true, force: true });
  fs.rmSync(path.join(work, `${videoName}.log`), { force: true });
  const renderEnv = { ...process.env };
  delete renderEnv.NODE_V8_COVERAGE;
  const render = spawnSync(
    process.execPath,
    [
      'dist/src/render.js', fixturePath,
      '--project', 'test/fixtures',
      '--out', renderOutput,
      '--no-voice',
      '--raw-audio',
    ],
    { encoding: 'utf8', timeout: 420_000, env: renderEnv },
  );
  assert.equal(render.status, 0, `${render.stdout}\n${render.stderr}`);

  const rendered = path.join(renderOutput, `${videoName}.mp4`);
  const video = path.join(output, `${videoName}.mp4`);
  fs.copyFileSync(rendered, video);
  assert.ok(fs.statSync(video).size > 10_000, `${videoName}.mp4 should contain rendered building footage`);
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
  const videoStream = metadata.streams.find(({ codec_type }) => codec_type === 'video');
  assert.deepEqual([videoStream?.width, videoStream?.height], [640, 360]);
  assert.ok(Number(metadata.format.duration) >= 5.9, 'Asakusa building video should be six seconds');
});

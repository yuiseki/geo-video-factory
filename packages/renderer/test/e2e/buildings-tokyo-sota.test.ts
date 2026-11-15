import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { prepareVideoOutput } from './video-e2e.js';
import { wipeSequenceFilter, type WipeKeys } from '../../src/compose.js';

const videoName = 'buildings-tokyo-sota';
const baselineFixture = 'buildings-tokyo-sota-baseline.json';
const enhancedFixture = 'buildings-tokyo-sota-enhanced.json';
const preludeFixture = 'buildings-tokyo-sota-prelude.json';
const preludeEnhancedFixture = 'buildings-tokyo-sota-prelude-enhanced.json';
const prepareScript = 'test/e2e/prepare-buildings-tokyo-sota.py';
// Before/after slider: fraction of the width (from the left) that shows the baseline.
// Opening (11 s): West Shinjuku as PLATEAU shows it, swept to the enhanced render, then 35 km west.
const preludeWipe: WipeKeys = [[0, 1], [1.2, 1], [3.4, 0.5], [4.4, 0.5], [5.2, 0], [11, 0]];
// Main part (times within it): Hamura rises and is painted, then the border and the final sweep.
const wipe: WipeKeys = [[0, 0], [20, 0], [21.5, 0.5], [30.5, 0.5], [32, 0], [40.5, 0], [42, 1], [43, 1], [46.5, 0], [49, 0]];

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

function renderVariant(project: string, fixture: string, outDir: string, name: string): string {
  fs.rmSync(outDir, { recursive: true, force: true });
  const renderEnv = { ...process.env };
  delete renderEnv.NODE_V8_COVERAGE;
  const render = spawnSync(
    process.execPath,
    [
      'dist/src/render.js',
      path.join(project, fixture),
      '--project', project,
      '--out', outDir,
      '--no-voice',
      '--raw-audio',
    ],
    { encoding: 'utf8', timeout: 3_600_000, env: renderEnv },
  );
  assert.equal(render.status, 0, `${name}\n${render.stdout}\n${render.stderr}`);
  return path.join(outDir, `${path.basename(outDir)}.mp4`);
}

const target = process.env.VIDEO_TARGET?.trim();

test(`E2E: renderer writes ${videoName}.mp4`, {
  timeout: 9_000_000,
  skip: Boolean(target && target !== videoName),
}, () => {
  const output = path.resolve('dist/test/video');
  const work = path.join(output, '.work');
  const renderOutput = path.join(work, videoName);
  const generatedProject = path.join(renderOutput, 'project');
  prepareVideoOutput(output, work);

  // The pipeline needs packages/pipeline/requirements-dev.txt (DracoPy, shapely); point
  // GVF_PYTHON at an interpreter that has them.
  const pythonCmd = process.env.GVF_PYTHON ?? (process.platform === 'win32' ? 'python' : 'python3');
  const prepare = spawnSync(pythonCmd, [prepareScript, generatedProject], {
    cwd: process.cwd(),
    encoding: 'utf8',
    timeout: 900_000,
  });
  assert.equal(prepare.status, 0, `${videoName} asset preparation\n${prepare.stdout}\n${prepare.stderr}`);

  const preludeVideo = renderVariant(
    generatedProject,
    preludeFixture,
    path.join(renderOutput, 'render', 'prelude'),
    'buildings-tokyo-sota-prelude',
  );
  const preludeEnhancedVideo = renderVariant(
    generatedProject,
    preludeEnhancedFixture,
    path.join(renderOutput, 'render', 'prelude-enhanced'),
    'buildings-tokyo-sota-prelude-enhanced',
  );
  const baselineVideo = renderVariant(
    generatedProject,
    baselineFixture,
    path.join(renderOutput, 'render', 'baseline'),
    'buildings-tokyo-sota-baseline',
  );
  const enhancedVideo = renderVariant(
    generatedProject,
    enhancedFixture,
    path.join(renderOutput, 'render', 'enhanced'),
    'buildings-tokyo-sota-enhanced',
  );

  const finalVideo = path.join(output, `${videoName}.mp4`);
  const compose = spawnSync(
    'ffmpeg',
    [
      '-y',
      '-i', preludeVideo,
      '-i', preludeEnhancedVideo,
      '-i', baselineVideo,
      '-i', enhancedVideo,
      '-filter_complex',
      wipeSequenceFilter([preludeWipe, wipe], 4),
      '-map', '[v]',
      '-c:v', 'libx264',
      '-pix_fmt', 'yuv420p',
      '-crf', '18',
      '-preset', 'medium',
      '-movflags', '+faststart',
      finalVideo,
    ],
    { encoding: 'utf8', timeout: 300_000 },
  );
  assert.equal(compose.status, 0, `ffmpeg slider composition failed\n${compose.stderr}`);
  assert.ok(fs.statSync(finalVideo).size > 1_000, `${videoName}.mp4 should not be empty`);

  const metadata = probeVideo(finalVideo);
  assert.deepEqual([metadata.width, metadata.height], [1280, 720]);
  assert.ok(metadata.duration >= 59.5, `${videoName}.mp4 is too short`);
});

test(`${videoName} E2E fixtures configure a 720p before/after slider of baseline vs enhanced`, () => {
  assert.match(videoName, /^buildings-/);
  assert.ok(fs.existsSync(prepareScript));
  const baseline = JSON.parse(fs.readFileSync(path.join('test/fixtures', baselineFixture), 'utf8'));
  const enhanced = JSON.parse(fs.readFileSync(path.join('test/fixtures', enhancedFixture), 'utf8'));
  const prelude = JSON.parse(fs.readFileSync(path.join('test/fixtures', preludeFixture), 'utf8'));
  const seconds = (spec: { shots: { duration: number }[] }) => spec.shots.reduce((sum, s) => sum + s.duration, 0);

  for (const spec of [baseline, enhanced]) {
    assert.equal(spec.width, 1280);
    assert.equal(spec.height, 720);
  }
  assert.deepEqual(baseline.plateauBuildings.reveal, enhanced.plateauBuildings.reveal);
  assert.equal(wipe[wipe.length - 1]![0], seconds(baseline));
  // On-screen text states counts and names; no mood copy ("AI poem") and no overclaiming.
  const text = JSON.stringify([prelude, baseline, enhanced]);
  for (const word of ['全部', 'すべて', 'つながる', '革命', '魔法', '可能性', '誰でも']) {
    assert.ok(!text.includes(word), `on-screen text must not use "${word}"`);
  }
  assert.equal(baseline.plateauBuildings?.appearance, false);
  assert.equal(enhanced.plateauBuildings?.appearance, true);
  assert.equal(baseline.shots.length, enhanced.shots.length);
  assert.equal(seconds(prelude) + seconds(baseline), 60);
  assert.deepEqual([prelude.width, prelude.height], [1280, 720]);
  const preludeEnhanced = JSON.parse(fs.readFileSync(path.join('test/fixtures', preludeEnhancedFixture), 'utf8'));
  assert.equal(prelude.plateauBuildings.appearance, false);
  assert.equal(preludeEnhanced.plateauBuildings.appearance, true);
  for (let i = 0; i < prelude.shots.length; i++) {
    assert.deepEqual(prelude.shots[i].from, preludeEnhanced.shots[i].from);
    assert.deepEqual(prelude.shots[i].to, preludeEnhanced.shots[i].to);
  }
  assert.equal(preludeWipe[preludeWipe.length - 1]![0], seconds(prelude));
  assert.deepEqual(prelude.shots.at(-1).to, baseline.shots[0].from, 'the opening lands where the main part starts');
  for (let i = 0; i < baseline.shots.length; i++) {
    assert.deepEqual(baseline.shots[i].from, enhanced.shots[i].from);
    assert.deepEqual(baseline.shots[i].to, enhanced.shots[i].to);
    assert.equal(baseline.shots[i].duration, enhanced.shots[i].duration);
  }
});

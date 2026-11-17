import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { pipelinePython, prepareVideoOutput } from './video-e2e.js';
import { layerFormat, overlayFilter, type RenderLayer } from '../../src/compose.js';

const videoName = 'buildings-tokyo-sota';
const fixture = 'buildings-tokyo-sota.json';
const prepareScript = 'test/e2e/prepare-buildings-tokyo-sota.py';

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

function renderLayer(project: string, outDir: string, layer: RenderLayer): string {
  fs.rmSync(outDir, { recursive: true, force: true });
  const renderEnv = { ...process.env };
  delete renderEnv.NODE_V8_COVERAGE;
  const render = spawnSync(
    process.execPath,
    ['dist/src/render.js', path.join(project, fixture), '--project', project, '--out', outDir, '--no-voice', '--layer', layer],
    { encoding: 'utf8', timeout: 3_600_000, env: renderEnv },
  );
  assert.equal(render.status, 0, `${layer}\n${render.stdout}\n${render.stderr}`);
  return path.join(outDir, `${path.basename(outDir)}.${layerFormat(layer).video}`);
}

const target = process.env.VIDEO_TARGET?.trim();

test(`E2E: renderer writes ${videoName}.mp4`, {
  timeout: 7_200_000,
  skip: Boolean(target && target !== videoName),
}, () => {
  const output = path.resolve('dist/test/video');
  const work = path.join(output, '.work');
  const renderOutput = path.join(work, videoName);
  const generatedProject = path.join(renderOutput, 'project');
  prepareVideoOutput(output, work);

  const prepare = spawnSync(pipelinePython(), [prepareScript, generatedProject], { cwd: process.cwd(), encoding: 'utf8', timeout: 1_800_000 });
  assert.equal(prepare.status, 0, `${videoName} asset preparation\n${prepare.stdout}\n${prepare.stderr}`);

  // One continuous render of the picture, then the decorations as their own transparent layer,
  // laid over at the end (text is never baked into the 3D render).
  const picture = renderLayer(generatedProject, path.join(renderOutput, 'render', 'map'), 'map');
  const decorations = renderLayer(generatedProject, path.join(renderOutput, 'render', 'overlay'), 'overlay');

  const finalVideo = path.join(output, `${videoName}.mp4`);
  const compose = spawnSync(
    'ffmpeg',
    ['-y', '-i', picture, '-i', decorations, '-filter_complex', overlayFilter(), '-map', '[v]',
      '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-preset', 'medium', '-movflags', '+faststart', finalVideo],
    { encoding: 'utf8', timeout: 600_000 },
  );
  assert.equal(compose.status, 0, `ffmpeg overlay failed\n${compose.stderr}`);
  const metadata = probeVideo(finalVideo);
  assert.deepEqual([metadata.width, metadata.height], [1280, 720]);
  assert.ok(metadata.duration >= 59.5, `${videoName}.mp4 is too short`);
});

test(`${videoName} fixture: one continuous 60 s render from West Shinjuku to Hamura`, () => {
  assert.match(videoName, /^buildings-/);
  assert.ok(fs.existsSync(prepareScript));
  const spec = JSON.parse(fs.readFileSync(path.join('test/fixtures', fixture), 'utf8'));
  assert.deepEqual([spec.width, spec.height], [1280, 720]);
  assert.equal(spec.shots.reduce((sum: number, s: { duration: number }) => sum + s.duration, 0), 60);
  const groups = spec.plateauBuildings as { manifest: string; reveal: { paint: [number, number][] } }[];
  assert.equal(groups.length, 2, 'Shinjuku and Hamura/Fussa in one render');
  assert.match(groups[0]!.manifest, /shinjuku/);
  // the Tokyo Metropolitan Government Building stays on screen long enough to be looked at
  const first = spec.shots[0] as { duration: number; overlays: { text?: string }[] };
  assert.ok(first.duration >= 8 && first.overlays.some((o) => o.text === '東京都庁'));
  // untextured buildings change in place: the paint waves start after the opening look
  assert.ok(groups[0]!.reveal.paint[0]![1] < 0 && groups[1]!.reveal.paint[0]![1] < 0);
  // On-screen text states counts and names; no mood copy ("AI poem") and no overclaiming.
  const text = JSON.stringify(spec);
  // and no jargon a viewer cannot read (較正: say what was measured and borrowed instead)
  for (const word of ['全部', 'すべて', 'つながる', '革命', '魔法', '可能性', '誰でも', '較正']) {
    assert.ok(!text.includes(word), `on-screen text must not use "${word}"`);
  }
});

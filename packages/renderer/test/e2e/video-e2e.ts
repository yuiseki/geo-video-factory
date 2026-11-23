import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { blankFrames, evaluatePerf, parseFrameCount, parseSignalStats, readBaseline, updateBaseline } from '../support/perf.js';

const PERF_BASELINE = path.resolve('test/perf-baseline.json');

/** Per-frame luma of the finished video (640x360 is cheap): catches a black or washed-out render. */
export function lumaFrames(video: string) {
  const r = spawnSync(
    'ffmpeg',
    ['-v', 'error', '-i', video, '-vf', 'signalstats,metadata=mode=print:file=-', '-f', 'null', '-'],
    { encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 },
  );
  assert.equal(r.status, 0, r.stderr);
  return parseSignalStats(r.stdout);
}

export interface VideoCase {
  name: string;
  fixture: string;
  minimumDuration: number;
  prepareScript?: string;
  generatedProject?: boolean;
  outputPath?: string;
  width?: number;
  height?: number;
  noVoice?: boolean;
  expectAudio?: boolean;
  skipReason?: string;
  /** Frames allowed to be blank (e.g. an intended fade from black). Default 0. */
  allowBlankFrames?: number;
}

/**
 * The interpreter for the prepare scripts. They import packages/pipeline, which needs
 * packages/pipeline/requirements-dev.txt (DracoPy, shapely); point GVF_PYTHON at an interpreter
 * that has them when the default one does not.
 */
export function pipelinePython(
  env: Record<string, string | undefined> = process.env,
  platform: string = process.platform,
): string {
  return env.GVF_PYTHON ?? (platform === 'win32' ? 'python' : 'python3');
}

export function prepareVideoOutput(output: string, work: string): void {
  fs.mkdirSync(output, { recursive: true });
  fs.mkdirSync(work, { recursive: true });
}

function probeVideo(video: string): { width: number; height: number; duration: number; hasAudio: boolean } {
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
  const hasAudio = metadata.streams.some(({ codec_type }) => codec_type === 'audio');
  return { width: stream.width, height: stream.height, duration: Number(metadata.format.duration), hasAudio };
}

/** Render speed (browser start, tile loads, frames, encode) per frame, against test/perf-baseline.json. */
export function checkRenderSpeed(name: string, frames: number, renderMs: number, record?: string): void {
  const current = { frames, msPerFrame: renderMs / frames };
  if (record) fs.writeFileSync(record, JSON.stringify({ ...current, renderMs }, null, 2) + '\n');
  console.log(`perf ${name}: ${current.msPerFrame.toFixed(0)} ms/frame over ${frames} frames`);
  if (process.env.GVF_PERF_UPDATE === '1') {
    updateBaseline(PERF_BASELINE, name, current);
    return;
  }
  const verdict = evaluatePerf(name, current, readBaseline(PERF_BASELINE), {
    factor: process.env.GVF_PERF_FACTOR ? Number(process.env.GVF_PERF_FACTOR) : undefined,
    off: process.env.GVF_PERF === 'off',
  });
  assert.ok(verdict.ok, verdict.message);
}

export function registerVideoE2E(item: VideoCase): void {
  const target = process.env.VIDEO_TARGET?.trim();
  const skip = Boolean(target && target !== item.name) || item.skipReason || false;
  test(`E2E: renderer writes ${item.name}.mp4`, { timeout: 1_000_000, skip }, () => {
    const output = path.resolve('dist/test/video');
    const work = path.join(output, '.work');
    const renderOutput = path.join(work, item.name);
    const generatedProject = path.join(renderOutput, 'project');
    prepareVideoOutput(output, work);

    if (item.prepareScript) {
      const prepare = spawnSync(pipelinePython(), [item.prepareScript, generatedProject, item.fixture], {
        cwd: process.cwd(),
        encoding: 'utf8',
        timeout: 900_000,
      });
      assert.equal(prepare.status, 0, `${item.name} asset preparation\n${prepare.stdout}\n${prepare.stderr}`);
    }

    const frameOutput = path.join(renderOutput, 'render', item.name);
    fs.rmSync(frameOutput, { recursive: true, force: true });
    const project = item.generatedProject ? generatedProject : 'test/fixtures';
    const renderEnv = { ...process.env };
    delete renderEnv.NODE_V8_COVERAGE;
    const renderArgs = [
      'dist/src/render.js',
      path.join(project, item.fixture),
      '--project', project,
      '--out', frameOutput,
      ...(item.noVoice === false ? [] : ['--no-voice']),
      '--raw-audio',
    ];
    const startedAt = performance.now();
    const render = spawnSync(process.execPath, renderArgs, { encoding: 'utf8', timeout: 420_000, env: renderEnv });
    const renderMs = performance.now() - startedAt;
    assert.equal(render.status, 0, `${item.name}\n${render.stdout}\n${render.stderr}`);
    const frames = parseFrameCount(render.stdout);
    assert.ok(frames && frames > 0, `${item.name}: renderer did not report a frame count\n${render.stdout}`);
    assert.doesNotMatch(render.stderr, /captured before all tiles loaded/, `${item.name}: some frames were captured before their tiles loaded`);
    assert.doesNotMatch(render.stderr, /\[http (4|5)\d\d\]/, `${item.name}: a request failed\n${render.stderr}`);

    const rendered = path.join(frameOutput, `${item.name}.mp4`);
    const video = path.join(output, item.outputPath ?? `${item.name}.mp4`);
    if (item.outputPath) {
      fs.rmSync(path.dirname(video), { recursive: true, force: true });
      fs.mkdirSync(path.dirname(video), { recursive: true });
    }
    fs.copyFileSync(rendered, video);
    if (item.outputPath) fs.rmSync(path.join(output, `${item.name}.mp4`), { force: true });
    assert.ok(fs.statSync(video).size > 1_000, `${item.name}.mp4 should not be empty`);
    const metadata = probeVideo(video);
    assert.deepEqual([metadata.width, metadata.height], [item.width ?? 640, item.height ?? 360]);
    assert.ok(metadata.duration >= item.minimumDuration, `${item.name}.mp4 is too short`);
    if (item.expectAudio) assert.ok(metadata.hasAudio, `${item.name}.mp4 must contain an audio stream`);

    const luma = lumaFrames(video);
    assert.equal(luma.length, frames, `${item.name}.mp4 holds ${luma.length} frames, the renderer wrote ${frames}`);
    const blank = blankFrames(luma);
    assert.ok(blank.length <= (item.allowBlankFrames ?? 0), `${item.name}.mp4 has blank frames at ${blank.slice(0, 10).join(', ')}`);

    checkRenderSpeed(item.name, frames, renderMs, path.join(renderOutput, 'perf.json'));
  });
}

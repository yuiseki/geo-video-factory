import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

export interface VideoCase {
  name: string;
  fixture: string;
  minimumDuration: number;
  prepareScript?: string;
  generatedProject?: boolean;
  outputPath?: string;
  width?: number;
  height?: number;
}

export function prepareVideoOutput(output: string, work: string): void {
  fs.mkdirSync(output, { recursive: true });
  fs.mkdirSync(work, { recursive: true });
}

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

export function registerVideoE2E(item: VideoCase): void {
  const target = process.env.VIDEO_TARGET?.trim();
  test(`E2E: renderer writes ${item.name}.mp4`, { timeout: 1_000_000, skip: Boolean(target && target !== item.name) }, () => {
    const output = path.resolve('dist/test/video');
    const work = path.join(output, '.work');
    const renderOutput = path.join(work, item.name);
    const generatedProject = path.join(renderOutput, 'project');
    prepareVideoOutput(output, work);

    if (item.prepareScript) {
      const prepare = spawnSync('python3', [item.prepareScript, generatedProject, item.fixture], {
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
    const render = spawnSync(
      process.execPath,
      [
        'dist/src/render.js',
        path.join(project, item.fixture),
        '--project', project,
        '--out', frameOutput,
        '--no-voice',
        '--raw-audio',
      ],
      { encoding: 'utf8', timeout: 420_000, env: renderEnv },
    );
    assert.equal(render.status, 0, `${item.name}\n${render.stdout}\n${render.stderr}`);

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
  });
}

// Render a shot list (JSON) to JPEG frames and an mp4.
//   node dist/src/render.js shots/example.json [--project dir] [--out out/example] [--fps 30] [--size 1920x1080]
//                   [--stills 1.5]   only one frame every 1.5 s (preview, no mp4)
//                   [--from 3 --to 8]  render part of the timeline
//                   [--no-voice]     skip VOICEVOX; time the lines from their length (draft)
//                   [--raw-audio]    skip loudnorm/BGM mixing
//                   [--check-label-overlap]
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { prepareNarration } from './voice.js';
import type { ShotSpec } from './types.js';

const PACKAGE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

const TYPES: Record<string, string> = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.mjs': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.map': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
};

export function contentType(file: string): string {
  return TYPES[path.extname(file)] ?? 'application/octet-stream';
}

export function resolveProjectRoot(specPath: string, projectArg?: string): string {
  if (projectArg) return path.resolve(projectArg);
  const absSpec = path.resolve(specPath);
  const parent = path.dirname(absSpec);
  return path.basename(parent) === 'shots' ? path.dirname(parent) : process.cwd();
}

export function parseSize(value: string): [number, number] {
  const match = /^(\d+)x(\d+)$/.exec(value);
  if (!match) throw new Error(`invalid size "${value}"; expected WIDTHxHEIGHT`);
  const width = Number(match[1]);
  const height = Number(match[2]);
  if (!Number.isSafeInteger(width) || !Number.isSafeInteger(height) || width <= 0 || height <= 0) {
    throw new Error(`invalid size "${value}"; dimensions must be positive integers`);
  }
  return [width, height];
}

export function buildFrameTimes(from: number, to: number, step: number): number[] {
  if (!Number.isFinite(from) || from < 0) throw new Error('from must be a non-negative number');
  if (!Number.isFinite(to) || to < from) throw new Error('invalid frame range: to must be at least from');
  if (!Number.isFinite(step) || step <= 0) throw new Error('step must be a positive number');
  const count = Math.max(0, Math.ceil((to - from - 1e-9) / step));
  return Array.from({ length: count }, (_, i) => Number((from + i * step).toFixed(12)));
}

export function resolveWorkerCount(frameCount: number, explicit?: number): number {
  if (explicit !== undefined) {
    if (!Number.isSafeInteger(explicit) || explicit < 1) throw new Error(`invalid workers "${explicit}"; expected positive integer`);
    return Math.min(explicit, Math.max(1, frameCount));
  }
  return frameCount >= 24 ? 4 : 1;
}

export function partitionFrameIndices(frameCount: number, workers: number): Array<[number, number]> {
  if (frameCount <= 0) return [];
  const count = Math.min(Math.max(1, workers), frameCount);
  const base = Math.floor(frameCount / count);
  const extra = frameCount % count;
  const ranges: Array<[number, number]> = [];
  let start = 0;
  for (let i = 0; i < count; i++) {
    const end = start + base + (i < extra ? 1 : 0);
    ranges.push([start, end]);
    start = end;
  }
  return ranges;
}

function isWithin(root: string, target: string): boolean {
  const rel = path.relative(root, target);
  return rel !== '' && !rel.startsWith('..') && !path.isAbsolute(rel);
}

export function chromiumGlArgs(platform: NodeJS.Platform = process.platform, flyoverGl = process.env.FLYOVER_GL): string[] {
  if (flyoverGl === 'swiftshader') {
    return ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'];
  }
  const angle = platform === 'win32' ? 'd3d11' : platform === 'darwin' ? 'metal' : 'gl-egl';
  return ['--use-gl=angle', `--use-angle=${angle}`, '--ignore-gpu-blocklist'];
}

export function resolveRequestFile(urlPath: string, packageRoot: string, projectRoot: string): string | null {
  let clean: string;
  try {
    clean = decodeURIComponent(new URL(urlPath, 'http://x').pathname).replace(/^\/+/, '');
  } catch {
    return null;
  }
  let baseRoot: string;
  let candidate: string;

  if (clean === 'page/index.html' || clean === 'page/flyover.css') {
    baseRoot = path.join(packageRoot, 'public');
    candidate = path.join(baseRoot, path.basename(clean));
  } else if (clean === 'page/flyover.js' || clean === 'page/maplibre-gl-worker.mjs') {
    baseRoot = path.join(packageRoot, 'dist', 'src', 'page');
    candidate = path.join(baseRoot, path.basename(clean));
  } else if (clean === 'lib.js' || clean === 'page/lib.js') {
    baseRoot = path.join(packageRoot, 'dist', 'src');
    candidate = path.join(baseRoot, 'lib.js');
  } else if (clean.startsWith('node_modules/')) {
    baseRoot = path.join(packageRoot, 'node_modules');
    candidate = path.join(packageRoot, clean);
  } else {
    baseRoot = projectRoot;
    candidate = path.join(projectRoot, clean);
  }

  if (!isWithin(baseRoot, candidate) && candidate !== baseRoot) return null;
  if (!fs.existsSync(candidate) || fs.statSync(candidate).isDirectory()) return null;
  return candidate;
}

declare global {
  interface Window {
    FLY_READY?: boolean;
    FLY: {
      init: (spec: ShotSpec) => Promise<'idle' | 'timeout'>;
      frame: (sec: number) => Promise<'idle' | 'timeout'>;
      totalSeconds: () => number;
    };
  }
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const opt = (name: string, def?: string): string | undefined => {
    const i = args.indexOf('--' + name);
    return i >= 0 ? args[i + 1] : def;
  };
  const specPath = args.find((a) => a.endsWith('.json'));
  if (!specPath) {
    console.error('usage: node render.js <shots.json> [--project dir] [--out dir] [--fps n] [--size WxH] [--stills sec] [--from s --to s]');
    process.exit(2);
  }

  const projectRoot = resolveProjectRoot(specPath, opt('project'));
  const spec = JSON.parse(fs.readFileSync(specPath, 'utf8')) as ShotSpec;
  const [w, h] = parseSize(opt('size', `${spec.width ?? 1920}x${spec.height ?? 1080}`) ?? '1920x1080');
  spec.width = w;
  spec.height = h;
  const fps = Number(opt('fps', String(spec.fps ?? 30)));
  const out = path.resolve(opt('out', path.join(projectRoot, 'out', path.basename(specPath, '.json')))!);

  // Keep every previous render intact; a fresh destination prevents old frames leaking into output.
  if (fs.existsSync(path.join(out, 'frames'))) {
    throw new Error(`output already contains frames: ${out}; choose a new --out directory`);
  }
  fs.mkdirSync(path.join(out, 'frames'), { recursive: true });

  // Narration first: it decides how long each shot with "lines" lasts and adds the subtitles.
  const narration = await prepareNarration(spec, out, {
    noVoice: args.includes('--no-voice'),
    projectDir: projectRoot,
  });
  if (narration.credits.length) {
    console.log('credits:', narration.credits.join(' / '), `(also in ${path.join(out, 'credits.txt')})`);
  }

  const server = http.createServer((req, res) => {
    const file = resolveRequestFile(req.url ?? '/', PACKAGE_ROOT, projectRoot);
    if (!file) {
      res.writeHead(404);
      res.end();
      return;
    }
    res.writeHead(200, { 'content-type': contentType(file) });
    fs.createReadStream(file).pipe(res);
  });
  await new Promise<void>((r) => server.listen(0, '127.0.0.1', r));
  const addr = server.address();
  const port = typeof addr === 'object' && addr ? addr.port : 0;

  // An X11 DISPLAY inherited over SSH can freeze headless WebGL; drop it for the browser.
  const env: NodeJS.ProcessEnv = { ...process.env };
  delete env.DISPLAY;
  delete env.WAYLAND_DISPLAY;
  // Pick an OS-appropriate ANGLE GPU backend (d3d11 on Windows, gl-egl on Linux, metal on macOS);
  // FLYOVER_GL=swiftshader forces the CPU path on machines without a GPU.
  const GL = chromiumGlArgs();
  const browser = await chromium.launch({ env, args: GL });
  const total = spec.shots.reduce((sum, shot) => sum + (shot.duration ?? 0), 0);
  const from = Number(opt('from', '0'));
  const to = Math.min(total, Number(opt('to', String(total))));
  const stills = opt('stills');
  const step = stills ? Number(stills) : 1 / fps;
  const times = buildFrameTimes(from, to, step);
  const workersOpt = opt('workers');
  const workers = resolveWorkerCount(times.length, workersOpt !== undefined ? Number(workersOpt) : undefined);
  const ranges = partitionFrameIndices(times.length, workers);

  let timeouts = 0;
  let completed = 0;
  const collisions = new Map<string, number>();
  const t0 = Date.now();

  const renderRange = async (workerIndex: number, [start, end]: [number, number]) => {
    const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    page.on('console', (m) => {
      if (m.type() === 'error' && !m.text().startsWith('Failed to load resource:')) console.error('[page]', m.text());
    });
    page.on('pageerror', (e) => console.error('[page]', e.message));
    page.on('response', (r) => {
      if (r.status() >= 400 && !(r.status() === 404 && r.url().includes('/xyz/dem_png/'))) {
        console.error(`[http ${r.status()}] ${r.url()}`);
      }
    });
    await page.goto(`http://127.0.0.1:${port}/page/index.html`);
    await page.waitForFunction(() => window.FLY_READY === true);
    if (workerIndex === 0) {
      console.log(
        'webgl:',
        await page.evaluate(() => {
          const g = document.createElement('canvas').getContext('webgl2');
          const d = g && g.getExtension('WEBGL_debug_renderer_info');
          return d ? g.getParameter(d.UNMASKED_RENDERER_WEBGL) : String(!!g);
        }),
      );
    }
    const first = await page.evaluate((s) => window.FLY.init(s), spec);
    if (first === 'timeout' && workerIndex === 0) console.error('warning: first load did not settle (tiles still loading?)');

    for (let i = start; i < end; i++) {
      const timeSec = times[i]!;
      let r = await page.evaluate((s) => window.FLY.frame(s), timeSec);
      if (r === 'timeout') {
        console.log(`retrying tile load for frame ${i}`);
        r = await page.evaluate((s) => window.FLY.frame(s), timeSec);
      }
      if (r === 'timeout') timeouts++;

      if (args.includes('--check-label-overlap')) {
        const overlaps = await page.evaluate(() => {
          const labels = [...document.querySelectorAll('#overlay .o.label')];
          const others = [...document.querySelectorAll('#overlay .o.reaction, #overlay .o.subtitle, #overlay .o.panel, #overlay .o.photo-marker-card')];
          const visible = (el: Element) => Number(getComputedStyle(el).opacity) > 0.1;
          const result: [string, string][] = [];
          for (let a = 0; a < labels.length; a++) {
            const x = labels[a]!;
            const ra = x.getBoundingClientRect();
            for (const b of [...labels.slice(a + 1), ...others]) {
              const rb = b.getBoundingClientRect();
              if (visible(x) && visible(b) && Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left) > 2 && Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top) > 2) {
                result.push([x.textContent?.trim() ?? '', b.classList.contains('label') ? (b.textContent?.trim() ?? '') : b.className]);
              }
            }
          }
          return result;
        });
        for (const pair of overlaps) {
          const key = JSON.stringify(pair);
          if (!collisions.has(key)) collisions.set(key, timeSec);
        }
      }

      await page.screenshot({ path: path.join(out, 'frames', String(i).padStart(5, '0') + '.jpg'), type: 'jpeg', quality: 95 });
      completed++;
      if (completed % 30 === 0 || completed === times.length) {
        process.stdout.write(`\r${completed}/${times.length} frames, ${((Date.now() - t0) / 1000).toFixed(0)} s`);
      }
    }
    await page.close();
  };

  await Promise.all(ranges.map((range, idx) => renderRange(idx, range)));
  process.stdout.write(`\r${times.length}/${times.length} frames, ${((Date.now() - t0) / 1000).toFixed(0)} s\n`);

  await browser.close();
  server.close();

  if (timeouts) console.error(`warning: ${timeouts} frame(s) were captured before all tiles loaded`);
  for (const [pair, sec] of collisions) console.error(`warning: label overlap at ${sec.toFixed(2)}s: ${pair}`);

  if (stills) {
    const sheet = path.join(out, 'stills.jpg');
    const cols = Math.min(4, times.length);
    const r = spawnSync(
      'ffmpeg',
      ['-v', 'error', '-y', '-i', path.join(out, 'frames', '%05d.jpg'), '-vf', `scale=480:-1,tile=${cols}x${Math.ceil(times.length / cols)}`, '-frames:v', '1', sheet],
      { stdio: 'inherit' },
    );
    if (r.status !== 0) {
      console.error('ffmpeg failed while creating stills sheet');
      process.exit(1);
    }
    console.log(`stills: ${sheet}`);
  } else {
    const mp4 = path.join(out, path.basename(out) + '.mp4');
    const partial = from > 0 || to < total;
    const ff = ['-v', 'error', '-y', '-framerate', String(fps), '-i', path.join(out, 'frames', '%05d.jpg')];
    let audio: string[] = [];

    if (narration.wav && !partial) {
      if (args.includes('--raw-audio')) {
        ff.push('-i', narration.wav);
        audio = ['-map', '0:v', '-map', '1:a', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2'];
      } else {
        const inputs = ['-i', narration.wav];
        if (spec.bgm?.src) {
          const bgmPath = path.isAbsolute(spec.bgm.src) ? spec.bgm.src : path.resolve(projectRoot, spec.bgm.src);
          inputs.push('-stream_loop', '-1', '-i', bgmPath);
        }
        const mixFilter = (v: number, b: number) =>
          spec.bgm?.src ? `[${b}:a]volume=${spec.bgm.volume ?? 0.12}[b];[${v}:a][b]amix=inputs=2:duration=first:normalize=0` : `[${v}:a]anull`;
        const mix = mixFilter(0, 1);
        const target = 'I=-14:TP=-1.5:LRA=11';
        const m = spawnSync('ffmpeg', ['-hide_banner', '-nostats', ...inputs, '-filter_complex', `${mix},loudnorm=${target}:print_format=json`, '-f', 'null', '-'], {
          encoding: 'utf8',
        });
        const j = JSON.parse(m.stderr.slice(m.stderr.lastIndexOf('{'), m.stderr.lastIndexOf('}') + 1)) as Record<string, string>;
        const second = `loudnorm=${target}:measured_I=${j.input_i}:measured_TP=${j.input_tp}:measured_LRA=${j.input_lra}:measured_thresh=${j.input_thresh}:offset=${j.target_offset}:linear=true`;
        ff.push(...inputs);
        audio = ['-filter_complex', `${mixFilter(1, 2)},${second}[a]`, '-map', '0:v', '-map', '[a]', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2'];
      }
    } else if (narration.wav) {
      console.error('note: --from/--to renders the picture only (no audio)');
    }

    const r = spawnSync(
      'ffmpeg',
      [
        ...ff,
        ...audio,
        '-c:v',
        'libx264',
        '-pix_fmt',
        'yuv420p',
        '-crf',
        '18',
        '-maxrate',
        '20M',
        '-bufsize',
        '40M',
        '-profile:v',
        'high',
        '-level:v',
        '4.1',
        '-g',
        String(fps * 2),
        '-movflags',
        '+faststart',
        mp4,
      ],
      { stdio: 'inherit' },
    );
    if (r.status !== 0) {
      console.error('ffmpeg failed');
      process.exit(1);
    }
    console.log(`video: ${mp4}`);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((err) => {
    console.error(err);
    process.exit(1);
  });
}

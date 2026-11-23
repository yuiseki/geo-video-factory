// Helpers for the video E2E: render-speed baseline and "is the picture blank" checks.
import fs from 'node:fs';

export interface PerfRecord {
  frames: number;
  msPerFrame: number;
}
export type PerfBaseline = Record<string, PerfRecord>;

/** Last "N/N frames" progress line printed by the renderer. */
export function parseFrameCount(stdout: string): number | null {
  const all = [...stdout.matchAll(/(\d+)\/(\d+) frames/g)];
  const last = all.at(-1);
  return last ? Number(last[2]) : null;
}

export interface PerfOptions {
  /** Allowed slowdown against the baseline (default 3: the baseline is one run, with network tiles). */
  factor?: number;
  /** Ignore slowdowns smaller than this many ms per frame (default 50). */
  minAbsMs?: number;
  off?: boolean;
}

export function evaluatePerf(
  name: string,
  current: PerfRecord,
  baseline: PerfBaseline,
  { factor = 3, minAbsMs = 50, off = false }: PerfOptions = {},
): { ok: boolean; message: string } {
  const ref = baseline[name];
  if (off || !ref) return { ok: true, message: ref ? 'perf check off' : `no baseline for ${name}` };
  const slower = current.msPerFrame > ref.msPerFrame * factor && current.msPerFrame - ref.msPerFrame > minAbsMs;
  if (!slower) return { ok: true, message: `${name}: ${current.msPerFrame.toFixed(0)} ms/frame (baseline ${ref.msPerFrame.toFixed(0)})` };
  return {
    ok: false,
    message:
      `${name} renders ${current.msPerFrame.toFixed(0)} ms/frame, more than ${factor}x the baseline ${ref.msPerFrame.toFixed(0)} ms/frame. ` +
      'If the slowdown is intended, re-measure with GVF_PERF_UPDATE=1 and commit test/perf-baseline.json; ' +
      'on a machine without a GPU set GVF_PERF=off.',
  };
}

export function readBaseline(file: string): PerfBaseline {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8')) as PerfBaseline;
  } catch {
    return {};
  }
}

export function updateBaseline(file: string, name: string, record: PerfRecord): void {
  const next = { ...readBaseline(file), [name]: { frames: record.frames, msPerFrame: Math.round(record.msPerFrame * 10) / 10 } };
  const sorted = Object.fromEntries(Object.entries(next).sort(([a], [b]) => a.localeCompare(b)));
  fs.writeFileSync(file, JSON.stringify(sorted, null, 2) + '\n');
}

export interface FrameStats {
  yavg: number;
  ymin: number;
  ymax: number;
}

/** ffmpeg `signalstats,metadata=print` output: one block of lavfi.signalstats.* lines per frame. */
export function parseSignalStats(text: string): FrameStats[] {
  const frames: FrameStats[] = [];
  let cur: Partial<FrameStats> = {};
  const flush = () => {
    if (cur.yavg !== undefined && cur.ymin !== undefined && cur.ymax !== undefined) frames.push(cur as FrameStats);
    cur = {};
  };
  for (const line of text.split('\n')) {
    if (line.startsWith('frame:')) flush();
    const m = /^lavfi\.signalstats\.(YMIN|YAVG|YMAX)=([-\d.]+)/.exec(line.trim());
    if (!m) continue;
    const v = Number(m[2]);
    if (m[1] === 'YMIN') cur.ymin = v;
    else if (m[1] === 'YAVG') cur.yavg = v;
    else cur.ymax = v;
  }
  flush();
  return frames;
}

/** Indices of frames that carry no picture: all black, all white, or flat (no luma spread). */
export function blankFrames(frames: FrameStats[], minSpread = 8): number[] {
  return frames.flatMap((f, i) => (f.ymax - f.ymin < minSpread ? [i] : []));
}

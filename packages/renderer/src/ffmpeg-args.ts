// Pure builders for the ffmpeg command lines and the --supersample option of render.ts.
import path from 'node:path';

const MAX_SUPERSAMPLE = 4;

/** `--supersample N`: render N times larger in each direction and scale down at encode. */
export function parseSupersample(value?: string): number {
  if (value === undefined) return 1;
  const n = Number(value);
  if (value.trim() === '' || !Number.isInteger(n) || n < 1 || n > MAX_SUPERSAMPLE) {
    throw new Error(`--supersample must be an integer from 1 to ${MAX_SUPERSAMPLE} (got "${value}")`);
  }
  return n;
}

export function supersampledSize([w, h]: [number, number], factor: number): [number, number] {
  return [w * factor, h * factor];
}

export function downscaleFilter([w, h]: [number, number], factor: number): string | null {
  return factor > 1 ? `scale=${w}:${h}:flags=lanczos` : null;
}

export function transparentEncodeArgs(out: string, vf?: string | null): string[] {
  return [...(vf ? ['-vf', vf] : []), '-c:v', 'qtrle', '-pix_fmt', 'argb', out];
}

export function mp4EncodeArgs(fps: number, mp4: string, vf?: string | null): string[] {
  return [
    ...(vf ? ['-vf', vf] : []),
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-maxrate', '20M', '-bufsize', '40M',
    '-profile:v', 'high', '-level:v', '4.1', '-g', String(fps * 2), '-movflags', '+faststart', mp4,
  ];
}

export function stillsSheetArgs(framesDir: string, frameExt: string, sheet: string, count: number): string[] {
  const cols = Math.min(4, count);
  return [
    '-v', 'error', '-y', '-i', path.join(framesDir, '%05d.' + frameExt),
    '-vf', `scale=480:-1,tile=${cols}x${Math.ceil(count / cols)}`, '-frames:v', '1', sheet,
  ];
}

export const LOUDNORM_TARGET = 'I=-14:TP=-1.5:LRA=11';

export function parseLoudnormJson(stderr: string): Record<string, string> {
  return JSON.parse(stderr.slice(stderr.lastIndexOf('{'), stderr.lastIndexOf('}') + 1)) as Record<string, string>;
}

export function loudnormSecondPass(j: Record<string, string>): string {
  return `loudnorm=${LOUDNORM_TARGET}:measured_I=${j.input_i}:measured_TP=${j.input_tp}:measured_LRA=${j.input_lra}:measured_thresh=${j.input_thresh}:offset=${j.target_offset}:linear=true`;
}

import type {
  CameraKey,
  CameraPathKind,
  CameraPose,
  DemConfig,
  DemSourceSpec,
  EaseKind,
  LngLat,
  ReactionSegment,
  Shot,
  TimeWindow,
} from './types.js';

// Pure helpers shared by the browser page and the node tests. No DOM, no MapLibre.

// GSI elevation PNG tiles (dem_png, dem5a_png ...): x = R*2^16 + G*2^8 + B,
// h = x*0.01 m when x < 2^23, h = (x - 2^24)*0.01 m when x > 2^23, x = 2^23 is no data.
// No data (sea, outside Japan) becomes 0 m so the terrain has no spikes.
export function gsiToTerrarium(r: number, g: number, b: number): number {
  const x = r * 65536 + g * 256 + b;
  if (x === 8388608) return 0;
  const h = x < 8388608 ? x * 0.01 : (x - 16777216) * 0.01;
  return Math.round(h * 100) / 100;
}

// Terrarium encoding used by MapLibre raster-dem (encoding: "terrarium").
export function terrariumRGB(h: number): [number, number, number] {
  const v = h + 32768;
  const r = Math.floor(v / 256);
  const g = Math.floor(v) % 256;
  const b = Math.floor((v - Math.floor(v)) * 256);
  return [r, g, b];
}

export const DEMS: Record<string, DemConfig> = {
  // 地理院 標高タイル(基盤地図情報 数値標高モデル)。z14 まで。海と国外は 0 m にする
  gsi: {
    tiles: ['gsidem://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png'],
    maxzoom: 14,
    tileSize: 256,
    credit: '標高：国土地理院(地理院タイル「標高タイル」)を加工',
  },
  // Mapterhorn (Copernicus GLO-30 等)。全球対応、tileSize 512、Terrarium 形式
  mapterhorn: {
    tiles: ['https://tiles.mapterhorn.com/{z}/{x}/{y}.webp'],
    maxzoom: 15,
    tileSize: 512,
    credit: '標高：© Mapterhorn and DEM source contributors',
  },
};

export function demSourceSpec(name = 'gsi'): DemSourceSpec {
  const dem = DEMS[name];
  if (!dem) throw new Error(`unknown dem: ${name}`);
  return {
    source: {
      type: 'raster-dem',
      tiles: dem.tiles,
      tileSize: dem.tileSize ?? 256,
      maxzoom: dem.maxzoom,
      encoding: 'terrarium',
    },
    credit: dem.credit,
  };
}

export function ease(kind: EaseKind | string, t: number): number {
  t = Math.min(1, Math.max(0, t));
  switch (kind) {
    case 'linear': return t;
    case 'smooth': return t * t * (3 - 2 * t);
    case 'in': return t * t * t;
    case 'out': return 1 - (1 - t) ** 3;
    case 'inOut':
    default: return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
  }
}

const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;
const mercY = (lat: number): number => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
const unmercY = (y: number): number => ((2 * Math.atan(Math.exp(y)) - Math.PI / 2) * 180) / Math.PI;

export interface CameraPathOptions {
  path?: CameraPathKind;
  curve?: number;
  width?: number;
  height?: number;
}

// van Wijk & Nuij (2003) coupled zoom+pan trajectory so screen-space optical flow stays smooth.
function flyPanAndZoom(
  a: CameraKey,
  b: CameraKey,
  u: number,
  { curve = 1.42, width = 1920, height = 1080 }: CameraPathOptions,
): { frac: number; zoom: number } {
  if (u <= 0) return { frac: 0, zoom: a.zoom };
  if (u >= 1) return { frac: 1, zoom: b.zoom };
  const dx = (b.center[0] - a.center[0]) / 360;
  const dy = (mercY(a.center[1]) - mercY(b.center[1])) / (2 * Math.PI);
  const u1 = Math.hypot(dx, dy);
  if (u1 < 1e-9) return { frac: u, zoom: lerp(a.zoom, b.zoom, u) };

  const span = Math.max(width, height) / 512;
  const w0 = span * 2 ** -a.zoom;
  const w1 = span * 2 ** -b.zoom;
  const rho = curve > 0 ? curve : 1.42;
  const rho2 = rho * rho;
  const rho4 = rho2 * rho2;
  const b0 = (w1 * w1 - w0 * w0 + rho4 * u1 * u1) / (2 * w0 * rho2 * u1);
  const b1 = (w1 * w1 - w0 * w0 - rho4 * u1 * u1) / (2 * w1 * rho2 * u1);
  const r0 = -Math.asinh(b0);
  const r1 = -Math.asinh(b1);
  const s = ((r1 - r0) / rho) * u;
  const coshR0 = Math.cosh(r0);
  const w = (w0 * coshR0) / Math.cosh(r0 + rho * s);
  const uPan = (w0 / rho2) * (coshR0 * Math.tanh(r0 + rho * s) - Math.sinh(r0));
  return {
    frac: Math.min(1, Math.max(0, uPan / u1)),
    zoom: Math.log2(span / w),
  };
}

// keys: [{t, center:[lng,lat], zoom, pitch, bearing}], t in 0..1 within the shot.
// Easing is applied to the whole shot, then keys are interpolated linearly (or coupled via van Wijk when path='fly').
export function cameraAt(
  keys: CameraKey[],
  t: number,
  easing: EaseKind = 'inOut',
  options: CameraPathOptions = {},
): Required<CameraPose> {
  const e = ease(easing, t);
  const first = keys[0];
  if (!first) throw new Error('cameraAt requires at least one key');
  if (keys.length === 1) {
    return {
      center: first.center,
      zoom: first.zoom,
      pitch: first.pitch ?? 0,
      bearing: first.bearing ?? 0,
    };
  }
  let i = 0;
  while (i < keys.length - 2 && e > keys[i + 1]!.t) i++;
  const a = keys[i]!;
  const b = keys[i + 1]!;
  const u = b.t === a.t ? 1 : Math.min(1, Math.max(0, (e - a.t) / (b.t - a.t)));
  let db = (b.bearing ?? 0) - (a.bearing ?? 0);
  db = ((db + 540) % 360) - 180;
  const { frac, zoom } =
    options.path === 'fly' ? flyPanAndZoom(a, b, u, options) : { frac: u, zoom: lerp(a.zoom, b.zoom, u) };
  const center: LngLat =
    frac <= 0
      ? a.center
      : frac >= 1
        ? b.center
        : [lerp(a.center[0], b.center[0], frac), unmercY(lerp(mercY(a.center[1]), mercY(b.center[1]), frac))];
  return {
    center,
    zoom,
    pitch: lerp(a.pitch ?? 0, b.pitch ?? 0, u),
    bearing: (a.bearing ?? 0) + db * u,
  };
}

// First `frac` of a polyline by planar length (fine for the short lines drawn on a map).
export function sliceLine(coords: LngLat[], frac: number): LngLat[] {
  const first = coords[0];
  if (!first) return [];
  if (frac <= 0) return [first, first];
  if (frac >= 1) return coords;
  const seg: number[] = [];
  let total = 0;
  for (let i = 1; i < coords.length; i++) {
    const p0 = coords[i - 1]!;
    const p1 = coords[i]!;
    const d = Math.hypot(p1[0] - p0[0], p1[1] - p0[1]);
    seg.push(d);
    total += d;
  }
  let left = total * frac;
  const out: LngLat[] = [first];
  for (let i = 1; i < coords.length; i++) {
    const s = seg[i - 1]!;
    const p0 = coords[i - 1]!;
    const p1 = coords[i]!;
    if (left >= s) {
      out.push(p1);
      left -= s;
      continue;
    }
    const u = s === 0 ? 0 : left / s;
    out.push([lerp(p0[0], p1[0], u), lerp(p0[1], p1[1], u)]);
    break;
  }
  return out;
}

/** A shot's camera keys: explicit `keys`, or a two-key move from `from` to `to` (either may stand in for the other). */
export function shotCameraKeys(shot: Shot): CameraKey[] {
  if (shot.keys) return shot.keys;
  const from = shot.from ?? shot.to!;
  const to = shot.to ?? shot.from!;
  return [{ t: 0, ...from }, { t: 1, ...to }];
}

export function locate(shots: Shot[], sec: number): { index: number; t: number; sec: number } {
  let start = 0;
  for (let i = 0; i < shots.length; i++) {
    const d = shots[i]!.duration ?? 0;
    if (sec < start + d || i === shots.length - 1) {
      const local = Math.min(d, Math.max(0, sec - start));
      return { index: i, t: d > 0 ? local / d : 0, sec: local };
    }
    start += d;
  }
  return { index: 0, t: 0, sec: 0 };
}

// window [t0, t1] in shot progress; fade is the ramp length in the same units.
export function fadeAlpha(win: TimeWindow | undefined, t: number, fade = 0.08): number {
  if (!win) return 1;
  const [t0, t1] = win;
  if (t < t0 || t > t1) return 0;
  const inA = fade > 0 ? Math.min(1, (t - t0) / fade) : 1;
  const outA = fade > 0 && t1 < 1 ? Math.min(1, (t1 - t) / fade) : 1;
  return Math.max(0, Math.min(inA, outA));
}


// One subtitle = one spoken line. Keep it to two rows: split a long line at the punctuation
// closest to the middle (or at the middle when there is none). Existing line breaks are kept.
export function wrapSubtitle(text: string, max = 26): string {
  if (text.includes('\n') || [...text].length <= max) return text;
  const chars = [...text];
  const mid = chars.length / 2;
  let best = -1;
  chars.forEach((c, i) => {
    if ('、。，,！？!?」）)'.includes(c) && i < chars.length - 1) {
      if (best < 0 || Math.abs(i + 1 - mid) < Math.abs(best - mid)) best = i + 1;
    }
  });
  if (best < 0 || Math.abs(best - mid) > chars.length * 0.3) best = Math.floor(mid);
  return chars.slice(0, best).join('') + '\n' + chars.slice(best).join('');
}

const round6 = (x: number): number => Math.round(x * 1e6) / 1e6;

// Lay spoken lines (their audio seconds) out in a shot: padStart, line, pause, line, ..., padEnd.
// The shot is stretched when the lines need more time than `duration`. Subtitle windows are in
// shot progress (0..1); each subtitle stays until the next line starts, the last one to the end.
export function layoutLines(
  secs: number[],
  { duration = 0, padStart = 0.3, pause = 0.25, padEnd = 0.4 }: { duration?: number; padStart?: number; pause?: number; padEnd?: number } = {},
): { duration: number; starts: number[]; windows: TimeWindow[] } {
  if (!secs.length) return { duration, starts: [], windows: [] };
  const starts: number[] = [];
  let t = padStart;
  secs.forEach((s, i) => {
    starts.push(round6(t));
    t += s + (i < secs.length - 1 ? pause : 0);
  });
  const need = round6(t + padEnd);
  const d = Math.max(duration, need);
  const windows: TimeWindow[] = starts.map((s, i) => [s / d, i < starts.length - 1 ? starts[i + 1]! / d : 1]);
  return { duration: d, starts, windows };
}

// Rough speech time for drafts without a voice engine (characters per second, punctuation ignored).
export function estimateSeconds(text: string, cps = 6.5): number {
  const n = [...text.replace(/[\s、。，,．.！？!?「」『』（）()…・]/g, '')].length;
  return Math.round((n / cps) * 100) / 100;
}

// ---- motion graphics helpers (everything is a function of time, so frames are reproducible) ----

// Seconds since an overlay's window opened and until it closes. A window that runs to the end of the
// shot never "leaves" (the cut ends it), so exits are only animated for windows closing inside the shot.
export function phase(win: TimeWindow | undefined, t: number, duration: number): { since: number; until: number; on: boolean } {
  const [t0, t1] = win ?? [0, 1];
  const r9 = (x: number) => Math.round(x * 1e9) / 1e9;
  return { since: r9((t - t0) * duration), until: t1 >= 1 ? Infinity : r9((t1 - t) * duration), on: t >= t0 && t <= t1 };
}

export function easeOutBack(x: number): number {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2;
}

// How many characters of a typewriter reveal are visible after `since` seconds at `cps` chars/second.
export function typeCount(text: string, since: number, cps = 28): number {
  return Math.max(0, Math.min([...text].length, Math.floor(since * cps + 1e-9)));
}

// A line chart's geometry: points ([YYYY-MM, value]) into a w x h box with padding [top, right, bottom, left].
// Returns pixel points, cumulative lengths along the line and the total length (for draw-on animation).
export function chartGeometry(
  points: [string, number][],
  { w, h, pad = [20, 20, 40, 60], ymin, ymax }: { w: number; h: number; pad?: [number, number, number, number]; ymin?: number; ymax?: number },
): { pts: [number, number][]; cum: number[]; length: number; lo: number; hi: number; plot: { x: number; y: number; w: number; h: number } } {
  const day = (s: string) => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, 1) / 86400000;
  const xs = points.map((p) => day(p[0]));
  const ys = points.map((p) => p[1]);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const lo = ymin ?? Math.min(...ys);
  const hi = ymax ?? Math.max(...ys);
  const [pt, pr, pb, pl] = pad;
  const pts: [number, number][] = xs.map((x, i) => [
    pl + ((x - x0) / (x1 - x0 || 1)) * (w - pl - pr),
    pt + (1 - (ys[i]! - lo) / (hi - lo || 1)) * (h - pt - pb),
  ]);
  const cum = [0];
  for (let i = 1; i < pts.length; i++) {
    cum.push(cum[i - 1]! + Math.hypot(pts[i]![0] - pts[i - 1]![0], pts[i]![1] - pts[i - 1]![1]));
  }
  return { pts, cum, length: cum[cum.length - 1]!, lo, hi, plot: { x: pl, y: pt, w: w - pl - pr, h: h - pt - pb } };
}

// Reaction wipe (character portraits in a corner).
// Loudness of a voice clip per video frame, scaled so the loudest frame is 1 (2 decimals).
export function levelEnvelope(samples: Int16Array | number[], rate: number, fps = 30): number[] {
  const per = rate / fps;
  const n = Math.floor(samples.length / per);
  const rms: number[] = [];
  for (let f = 0; f < n; f++) {
    let s = 0;
    const a = Math.round(f * per);
    const b = Math.round((f + 1) * per);
    for (let i = a; i < b; i++) {
      const sample = samples[i] ?? 0;
      s += sample * sample;
    }
    rms.push(Math.sqrt(s / Math.max(1, b - a)));
  }
  const max = Math.max(0, ...rms);
  return rms.map((v) => (max > 0 ? Math.round((v / max) * 100) / 100 : 0));
}

// Mouth open when the voice at time t (seconds since the clip started) is louder than thr.
export function mouthOpenAt(env: number[], t: number, fps = 30, thr = 0.15): boolean {
  const i = Math.floor(t * fps);
  return i >= 0 && i < env.length && env[i]! > thr;
}

function hash01(str: string): number {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 10000) / 10000;
}

// Eyes closed for `dur` seconds once per cycle; cycles last 0.7x to 1.3x `period`, varying per cycle
// and per character (seed), so two characters never blink in step. Pure function of time.
export function blinkAt(t: number, seed: string, { period = 4, dur = 0.13 }: { period?: number; dur?: number } = {}): boolean {
  if (t < 0) return false;
  let start = hash01(seed) * period;
  let k = 0;
  while (start + period * 1.3 < t && k < 100000) {
    start += period * (0.7 + 0.6 * hash01(seed + ':' + k));
    k++;
  }
  // step forward through cycles until the one containing t
  for (;;) {
    const len = period * (0.7 + 0.6 * hash01(seed + ':' + k));
    if (t < start + len) return t >= start && t < start + dur;
    start += len;
    k++;
  }
}

// The spoken line at time t (segments sorted by t0, end exclusive), with seconds since it began.
export function reactionAt(segs: ReactionSegment[], t: number): { seg: ReactionSegment; since: number } | null {
  for (const seg of segs) {
    if (t >= seg.t0 && t < seg.t1) return { seg, since: t - seg.t0 };
  }
  return null;
}

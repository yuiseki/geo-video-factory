/** Time-driven staging for 3D city scenes: the rising-buildings reveal and the day-to-night light. */
import { UPWARD_LAMBERT } from './city-tone.js';

export interface CityReveal {
  /** WGS84 point the wave of rising buildings starts from. */
  center: [number, number];
  /**
   * [seconds, meters] keys for the radius of the wave front. Buildings inside it stand; a
   * shrinking radius sinks them again (outer ones first), which reads as rewinding time.
   */
  radius: [number, number][];
  /** Width of the front in meters: a building rises over this distance. Defaults to 120. */
  width?: number;
  /**
   * [seconds, meters] keys for a second wave that paints the risen clay-white buildings with
   * their colors (orthophoto roofs, facades, windows). Without it buildings are painted.
   */
  paint?: [number, number][];
}

/** Linear interpolation over [seconds, value] keys; the first and last values hold outside. */
export function keyframeValue(keys: [number, number][] | undefined, t: number): number {
  if (!keys?.length) return 0;
  if (t <= keys[0]![0]) return keys[0]![1];
  for (let i = 1; i < keys.length; i++) {
    const [t1, v1] = keys[i]!;
    if (t <= t1) {
      const [t0, v0] = keys[i - 1]!;
      return t1 === t0 ? v1 : v0 + (v1 - v0) * (t - t0) / (t1 - t0);
    }
  }
  return keys[keys.length - 1]![1];
}

/** 0 (flat) .. 1 (standing) for a building `distance` meters from the reveal center at time t. */
export function revealProgress(reveal: CityReveal | undefined, t: number, distance: number): number {
  if (!reveal) return 1;
  const g = Math.min(1, Math.max(0, (revealRadius(reveal, t) - distance) / (reveal.width ?? 120)));
  return 1 - (1 - g) ** 3;
}

/** The front radius in meters that the shader compares against. */
export function revealRadius(reveal: CityReveal | undefined, t: number): number {
  return reveal ? keyframeValue(reveal.radius, t) : 1e9;
}

/** The paint front radius in meters (1e9, everything painted, when there are no paint keys). */
export function paintRadius(reveal: CityReveal | undefined, t: number): number {
  return reveal?.paint?.length ? keyframeValue(reveal.paint, t) : 1e9;
}

/** Meters east and north of origin, in the same local plane the city-proxy pipeline writes. */
export function localMeters(point: [number, number], origin: [number, number]): [number, number] {
  const kx = 111_320 * Math.cos(origin[1] * Math.PI / 180);
  return [(point[0] - origin[0]) * kx, (point[1] - origin[1]) * 110_950];
}

export interface CityLight {
  ambient: number;
  sun: number;
  /** Sky fill from the opposite side of the sun. */
  fill: number;
  sunColor: [number, number, number];
  ambientColor: [number, number, number];
  /** 0..1 how many windows glow. */
  windows: number;
  /** raster-brightness-max of the aerial photo. */
  mapBrightness: number;
  mapSaturation: number;
  /** Opacity of the ground shadows. */
  shadow: number;
}

const mix = (a: number, b: number, t: number) => a + (b - a) * t;
type Rgb = [number, number, number];
const mix3 = (a: Rgb, b: Rgb, t: number): Rgb =>
  [mix(a[0], b[0], t), mix(a[1], b[1], t), mix(a[2], b[2], t)];

/**
 * Where the lights stand, in the scene's east / north / up meters. The ground shadows are baked
 * for this sun (packages/pipeline/city_proxy.py SHADOW_PER_M).
 */
export const SUN_POSITION: readonly [number, number, number] = [-300, -450, 450];
export const FILL_POSITION: readonly [number, number, number] = [300, 200, 400];
/** Linear RGB of the sky fill (0xdce8ff). */
export const FILL_COLOR: Rgb = [0.716, 0.807, 1];

const luminance = (color: readonly number[]) => 0.2126 * color[0]! + 0.7152 * color[1]! + 0.0722 * color[2]!;
const upShare = (position: readonly number[]) => position[2]! / Math.hypot(position[0]!, position[1]!, position[2]!);

/**
 * Lambert gain of an upward face under a light: the luminance it returns per unit of albedo.
 * At 1 (with the specular, see UPWARD_LAMBERT) a roof shows its albedo as it is.
 */
export function upwardGain(light: Pick<CityLight, 'ambient' | 'ambientColor' | 'sun' | 'sunColor' | 'fill'>): number {
  return (
    light.ambient * luminance(light.ambientColor)
    + light.sun * luminance(light.sunColor) * upShare(SUN_POSITION)
    + light.fill * luminance(FILL_COLOR) * upShare(FILL_POSITION)
  ) / Math.PI;
}

/**
 * Light for night = 0 (day), 0.5 (dusk, warm low sun), 1 (night, moonlight and lit windows).
 * The balance of ambient, sun and fill is a look; their sum is not. It is scaled so that an
 * upward face is dimmed exactly as much as the aerial photo on the ground (mapBrightness), which
 * keeps roofs that carry the photo level with the ground at every hour.
 */
export function cityLight(night: number): CityLight {
  const n = Math.min(1, Math.max(0, night));
  const day: Rgb = [1, 0.905, 0.791]; // linear RGB of 0xfff4e6
  const dusk: Rgb = [1, 0.62, 0.36];
  const moon: Rgb = [0.62, 0.70, 0.95];
  const mapBrightness = n < 0.5 ? mix(1, 0.78, n * 2) : mix(0.78, 0.26, (n - 0.5) * 2);
  const balance = {
    ambient: mix(1.15, 0.22, n),
    ambientColor: mix3([1, 1, 1], [0.58, 0.63, 0.82], n),
    sun: n < 0.5 ? mix(0.85, 0.95, n * 2) : mix(0.95, 0.12, (n - 0.5) * 2),
    sunColor: n < 0.5 ? mix3(day, dusk, n * 2) : mix3(dusk, moon, (n - 0.5) * 2),
    fill: 0.35 * (1 - 0.7 * n),
  };
  // raster-brightness-max scales display values, the lights scale linear ones
  const scale = UPWARD_LAMBERT * mapBrightness ** 2.2 / upwardGain(balance);
  return {
    ...balance,
    ambient: balance.ambient * scale,
    sun: balance.sun * scale,
    fill: balance.fill * scale,
    windows: Math.min(1, Math.max(0, (n - 0.35) / 0.5)),
    mapBrightness,
    mapSaturation: mix(0, -0.45, n),
    shadow: n < 0.5 ? mix(0.38, 0.30, n * 2) : mix(0.30, 0, Math.min(1, (n - 0.5) * 3)),
  };
}

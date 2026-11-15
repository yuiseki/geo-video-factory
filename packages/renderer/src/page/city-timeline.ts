/** Time-driven staging for 3D city scenes: the rising-buildings reveal and the day-to-night light. */

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

/** Meters east and north of origin, in the same local plane the city-proxy pipeline writes. */
export function localMeters(point: [number, number], origin: [number, number]): [number, number] {
  const kx = 111_320 * Math.cos(origin[1] * Math.PI / 180);
  return [(point[0] - origin[0]) * kx, (point[1] - origin[1]) * 110_950];
}

export interface CityLight {
  ambient: number;
  sun: number;
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
const mix3 = (a: [number, number, number], b: [number, number, number], t: number): [number, number, number] =>
  [mix(a[0], b[0], t), mix(a[1], b[1], t), mix(a[2], b[2], t)];

/** Light for night = 0 (day), 0.5 (dusk, warm low sun), 1 (night, moonlight and lit windows). */
export function cityLight(night: number): CityLight {
  const n = Math.min(1, Math.max(0, night));
  const day: [number, number, number] = [1, 0.96, 0.9];
  const dusk: [number, number, number] = [1, 0.62, 0.36];
  const moon: [number, number, number] = [0.62, 0.70, 0.95];
  const sunColor = n < 0.5 ? mix3(day, dusk, n * 2) : mix3(dusk, moon, (n - 0.5) * 2);
  const ambientColor = mix3([1, 1, 1], [0.58, 0.63, 0.82], n);
  return {
    ambient: mix(1.15, 0.22, n),
    sun: n < 0.5 ? mix(0.85, 0.95, n * 2) : mix(0.95, 0.12, (n - 0.5) * 2),
    sunColor,
    ambientColor,
    windows: Math.min(1, Math.max(0, (n - 0.35) / 0.5)),
    mapBrightness: n < 0.5 ? mix(1, 0.78, n * 2) : mix(0.78, 0.26, (n - 0.5) * 2),
    mapSaturation: mix(0, -0.45, n),
    shadow: n < 0.5 ? mix(0.38, 0.30, n * 2) : mix(0.30, 0, Math.min(1, (n - 0.5) * 3)),
  };
}

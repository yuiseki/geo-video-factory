/**
 * Before/after slider: two renders of the same camera path combined in ffmpeg, with a vertical
 * divider whose position follows [seconds, fraction] keys. Left of the divider shows the first
 * input ("before"), right of it the second ("after"). Fraction 0 = all "after", 1 = all "before".
 */

export type WipeKeys = [number, number][];

/** Divider position (0..1 of the width) at time t; linear between keys, ends held. */
export function wipeAt(keys: WipeKeys, t: number): number {
  if (!keys.length) return 0;
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

const num = (value: number) => Number(value.toFixed(4)).toString();

/** The same piecewise-linear function as an ffmpeg expression of T. */
export function wipeExpression(keys: WipeKeys): string {
  if (!keys.length) return '0';
  let expr = num(keys[keys.length - 1]![1]);
  for (let i = keys.length - 1; i >= 1; i--) {
    const [t0, v0] = keys[i - 1]!;
    const [t1, v1] = keys[i]!;
    const segment = t1 === t0 ? num(v1) : `${num(v0)}+(${num(v1 - v0)})*(T-${num(t0)})/${num(t1 - t0)}`;
    expr = `if(lt(T,${num(t1)}),${segment},${expr})`;
  }
  return `if(lt(T,${num(keys[0]![0])}),${num(keys[0]![1])},${expr})`;
}

/**
 * ffmpeg -filter_complex graph: [0:v] before, [1:v] after -> [v]. A white divider `line` pixels
 * wide is drawn while the divider is inside the frame.
 */
export function wipeFilter(keys: WipeKeys, line = 4): string {
  const p = wipeExpression(keys);
  const half = line / 2;
  const blend = `if(lt(abs(X-W*(${p})),${half})*gt(${p},0.002)*lt(${p},0.998),255,if(lt(X,W*(${p})),A,B))`;
  return `[0:v]format=gbrp[a];[1:v]format=gbrp[b];[a][b]blend=all_expr='${blend}',format=yuv420p[v]`;
}

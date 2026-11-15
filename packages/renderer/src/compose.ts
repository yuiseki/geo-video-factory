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
 * ffmpeg -filter_complex graph: [before] and [after] -> [out] (default [0:v], [1:v] -> [v]). A
 * white divider `line` pixels wide is drawn while the divider is inside the frame.
 */
export function wipeFilter(keys: WipeKeys, line = 4, labels: { before?: string; after?: string; out?: string } = {}): string {
  const { before = '0:v', after = '1:v', out = 'v' } = labels;
  const p = wipeExpression(keys);
  const half = line / 2;
  const blend = `if(lt(abs(X-W*(${p})),${half})*gt(${p},0.002)*lt(${p},0.998),255,if(lt(X,W*(${p})),A,B))`;
  return `[${before}]format=gbrp[wa];[${after}]format=gbrp[wb];[wa][wb]blend=all_expr='${blend}',format=yuv420p[${out}]`;
}

/**
 * Several before/after sliders played one after another. Inputs come in pairs: part k uses input
 * 2k (before) and 2k+1 (after), with its own divider keys (times within that part).
 */
export function wipeSequenceFilter(parts: WipeKeys[], line = 4): string {
  const graphs = parts.map((keys, k) => wipeFilter(keys, line, { before: `${2 * k}:v`, after: `${2 * k + 1}:v`, out: `p${k}` }));
  const joined = parts.map((_, k) => `[p${k}]`).join('');
  return `${graphs.join(';')};${joined}concat=n=${parts.length}:v=1:a=0[v]`;
}

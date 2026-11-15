import { ease } from './lib.js';
import type { CounterOverlay } from './types.js';

/** The counter's numeric value at time t (null for text values). */
export function counterNumber(o: Pick<CounterOverlay, 'value' | 'countUp' | 'from' | 'countEase'>, t: number): number | null {
  if (typeof o.value !== 'number') return null;
  if (!o.countUp) return o.value;
  const [t0, t1] = o.countUp;
  const u = Math.min(1, Math.max(0, (t - t0) / (t1 - t0)));
  const from = o.from ?? 0;
  return from + (o.value - from) * (o.countEase === 'linear' ? u : ease('out', u));
}

/**
 * Positions of odometer wheels (most significant first) for a counting value: the ones wheel
 * turns continuously; a higher wheel moves only while every wheel below it rolls from 9 to 0.
 */
export function odometerColumns(value: number, digits: number): number[] {
  const v = Math.max(0, value);
  const out: number[] = [];
  for (let p = digits - 1; p >= 0; p--) {
    const unit = 10 ** p;
    const whole = Math.floor(v / unit) % 10;
    const carry = p === 0 ? v - Math.floor(v) : Math.min(1, Math.max(0, (v % unit) - (unit - 1)));
    out.push(Math.round((whole + carry) * 1e6) / 1e6);
  }
  return out;
}

export function countValue(o: Pick<CounterOverlay, 'value' | 'decimals' | 'countUp' | 'from' | 'countEase' | 'grouping'>, t: number): string {
  if (typeof o.value !== 'number') return String(o.value);
  const d = o.decimals ?? 0;
  let v = o.value;
  if (o.countUp) {
    const [t0, t1] = o.countUp;
    const u = Math.min(1, Math.max(0, (t - t0) / (t1 - t0)));
    const from = o.from ?? 0;
    v = from + (o.value - from) * (o.countEase === 'linear' ? u : ease('out', u));
  }
  return v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: o.grouping ?? true });
}

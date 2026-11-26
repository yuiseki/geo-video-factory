/** Position a map-anchored label in the overlay's 1920px design coordinate system. */
export function labelPosition(
  point: { x: number; y: number },
  scale: number,
  offset: [number, number] = [0, 0],
): { left: string; top: string } {
  return { left: `${point.x / scale + offset[0]}px`, top: `${point.y / scale + offset[1]}px` };
}

/** Resolve leader line and tag border colors for a label overlay. */
export function labelAccent(color?: string): {
  leaderStroke: string;
  tagStyle: Record<string, string>;
} {
  const c = color?.trim();
  if (!c) {
    return { leaderStroke: '#ffd36a', tagStyle: {} };
  }
  return {
    leaderStroke: c,
    tagStyle: { background: 'rgba(14, 22, 36, 0.90)', border: `3px solid ${c}` },
  };
}

/** Return true when any overlay is a fullscreen panel that replaces the map view. */
export function hasFullscreenPanel(overlays: Array<{ type: string; fullscreen?: boolean }> = []): boolean {
  return overlays.some((o) => o.type === 'panel' && o.fullscreen === true);
}

/** Compute clamped 0..1 expansion progress for a panel zooming from map card to fullscreen and back. */
export function panelExpandProgress(
  expand: [number, number] | undefined,
  t: number,
  collapse?: [number, number],
): number {
  if (!expand) return 0;
  const [e0, e1] = expand;
  if (t <= e0) return 0;
  if (t < e1 && e1 > e0) return Number(((t - e0) / (e1 - e0)).toFixed(12));
  if (!collapse) return 1;
  const [c0, c1] = collapse;
  if (t <= c0) return 1;
  if (t >= c1 || c1 <= c0) return 0;
  return Number((1 - (t - c0) / (c1 - c0)).toFixed(12));
}

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Linearly interpolate between two screen rectangles. */
export function lerpRect(from: Rect, to: Rect, p: number): Rect {
  return {
    x: from.x + (to.x - from.x) * p,
    y: from.y + (to.y - from.y) * p,
    w: from.w + (to.w - from.w) * p,
    h: from.h + (to.h - from.h) * p,
  };
}

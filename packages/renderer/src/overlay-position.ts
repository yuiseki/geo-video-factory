/** Position a map-anchored label in the overlay's 1920px design coordinate system. */
export function labelPosition(
  point: { x: number; y: number },
  scale: number,
  offset: [number, number] = [0, 0],
): { left: string; top: string } {
  return { left: `${point.x / scale + offset[0]}px`, top: `${point.y / scale + offset[1]}px` };
}

export type Ecef = [number, number, number];
export type LngLatHeight = [number, number, number];

const SEMI_MAJOR = 6378137;
const ECCENTRICITY_SQUARED = 6.69437999014e-3;

/** Ground-based proxy geometry already starts at map altitude zero. */
export function tileHeightOffset(kind: string | undefined, plateauOffset: number): number {
  return kind === 'osm-proxy' || kind === 'citygml-proxy' || kind === 'city-proxy' || kind === 'city-shadow' ? 0 : plateauOffset;
}

export function wgs84Ecef([longitude, latitude, height]: LngLatHeight): Ecef {
  const lambda = longitude * Math.PI / 180;
  const phi = latitude * Math.PI / 180;
  const sinPhi = Math.sin(phi);
  const radius = SEMI_MAJOR / Math.sqrt(1 - ECCENTRICITY_SQUARED * sinPhi * sinPhi);
  return [
    (radius + height) * Math.cos(phi) * Math.cos(lambda),
    (radius + height) * Math.cos(phi) * Math.sin(lambda),
    (radius * (1 - ECCENTRICITY_SQUARED) + height) * sinPhi,
  ];
}

export function ecefToEnu(point: Ecef, origin: LngLatHeight): Ecef {
  const reference = wgs84Ecef(origin);
  const delta = point.map((value, index) => value - reference[index]!) as Ecef;
  const lambda = origin[0] * Math.PI / 180;
  const phi = origin[1] * Math.PI / 180;
  const [dx, dy, dz] = delta;
  return [
    -Math.sin(lambda) * dx + Math.cos(lambda) * dy,
    -Math.sin(phi) * Math.cos(lambda) * dx - Math.sin(phi) * Math.sin(lambda) * dy + Math.cos(phi) * dz,
    Math.cos(phi) * Math.cos(lambda) * dx + Math.cos(phi) * Math.sin(lambda) * dy + Math.sin(phi) * dz,
  ];
}

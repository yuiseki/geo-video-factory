import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ecefToEnu, wgs84Ecef } from '../src/page/plateau-coordinates.js';

test('WGS84 origin maps to the local ENU origin', () => {
  const origin = wgs84Ecef([139.79, 35.7, 0]);
  assert.ok(ecefToEnu(origin, [139.79, 35.7, 0]).every((value) => Math.abs(value) < 1e-9));
});

test('ENU basis points east, north, and up at a Tokyo origin', () => {
  const origin: [number, number, number] = [139.79, 35.7, 0];
  const base = wgs84Ecef(origin);
  const east = ecefToEnu(wgs84Ecef([origin[0] + 0.00001, origin[1], 0]), origin);
  const north = ecefToEnu(wgs84Ecef([origin[0], origin[1] + 0.00001, 0]), origin);
  const up = ecefToEnu(wgs84Ecef([origin[0], origin[1], 1]), origin);
  assert.ok(east[0] > 0.9 && Math.abs(east[1]) < 0.01 && Math.abs(east[2]) < 0.01);
  assert.ok(north[1] > 1 && Math.abs(north[0]) < 0.01 && Math.abs(north[2]) < 0.01);
  assert.ok(Math.abs(up[2] - 1) < 1e-6);
  assert.equal(base.length, 3);
});

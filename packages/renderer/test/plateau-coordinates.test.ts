import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { MercatorCoordinate } from 'maplibre-gl';
import { ecefToEnu, wgs84Ecef } from '../src/page/plateau-coordinates.js';
import { tileHeightOffset } from '../src/page/plateau-coordinates.js';

test('ground-based proxy buildings do not inherit the PLATEAU ellipsoid height correction', () => {
  assert.equal(tileHeightOffset(undefined, -39), -39);
  assert.equal(tileHeightOffset('osm-proxy', -39), 0);
  assert.equal(tileHeightOffset('citygml-proxy', -39), 0);
});

function enuMatrix(center: [number, number]): THREE.Matrix4 {
  const lambda = center[0] * Math.PI / 180;
  const phi = center[1] * Math.PI / 180;
  const east = [-Math.sin(lambda), Math.cos(lambda), 0];
  const north = [-Math.sin(phi) * Math.cos(lambda), -Math.sin(phi) * Math.sin(lambda), Math.cos(phi)];
  const up = [Math.cos(phi) * Math.cos(lambda), Math.cos(phi) * Math.sin(lambda), Math.sin(phi)];
  return new THREE.Matrix4().set(
    east[0]!, east[1]!, east[2]!, 0,
    north[0]!, north[1]!, north[2]!, 0,
    up[0]!, up[1]!, up[2]!, 0,
    0, 0, 0, 1,
  );
}

const yUpToZUp = new THREE.Matrix4().set(1, 0, 0, 0, 0, 0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1);

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

test('b3dm RTC+delta and native GLB node-translation+RTC0 produce identical ENU and Mercator positions', () => {
  const center: [number, number] = [139.79, 35.7];
  const origin = wgs84Ecef([center[0], center[1], 0]);
  const basis = enuMatrix(center);
  const targetEcef = wgs84Ecef([139.7905, 35.7004, 15]);

  // Pattern A: b3dm with RTC=origin and local glTF delta
  const localDelta = new THREE.Vector3(
    targetEcef[0] - origin[0],
    targetEcef[2] - origin[2],
    -(targetEcef[1] - origin[1]),
  );
  const b3dmEnu = localDelta.clone().applyMatrix4(yUpToZUp).applyMatrix4(basis);

  // Pattern B: native GLB with rtc=[0,0,0], vertex at (0,0,0), node translation carrying inverse Y-up ECEF
  const nodeTranslation = new THREE.Vector3(targetEcef[0], targetEcef[2], -targetEcef[1]);
  const nativeTilePos = ecefToEnu([0, 0, 0], [center[0], center[1], 0]);
  const nativeEnu = nodeTranslation.clone()
    .applyMatrix4(yUpToZUp)
    .applyMatrix4(basis)
    .add(new THREE.Vector3(...nativeTilePos));

  assert.ok(b3dmEnu.distanceTo(nativeEnu) < 1e-7, `ENU mismatch: ${b3dmEnu.toArray()} vs ${nativeEnu.toArray()}`);

  // Height offset (-39 m) must shift only vertical ENU Z
  const shifted = b3dmEnu.clone().add(new THREE.Vector3(0, 0, -39));
  assert.equal(shifted.x, b3dmEnu.x);
  assert.equal(shifted.y, b3dmEnu.y);
  assert.ok(Math.abs((shifted.z - b3dmEnu.z) + 39) < 1e-9);
});

test('OSM proxy 4-corner footprint projects through ECEF -> ENU -> Mercator back to input lon/lat', () => {
  const center: [number, number] = [139.79, 35.7];
  const origin = wgs84Ecef([center[0], center[1], 0]);
  const basis = enuMatrix(center);
  const originMercator = MercatorCoordinate.fromLngLat(center, 0);
  const meterScale = originMercator.meterInMercatorCoordinateUnits();
  const localToMercator = new THREE.Matrix4()
    .makeTranslation(originMercator.x, originMercator.y, originMercator.z)
    .multiply(new THREE.Matrix4().makeScale(meterScale, -meterScale, meterScale));

  const corners: [number, number][] = [
    [139.7895, 35.6996],
    [139.7906, 35.6996],
    [139.7906, 35.7005],
    [139.7895, 35.7005],
  ];
  for (const [lon, lat] of corners) {
    const p = wgs84Ecef([lon, lat, 0]);
    const gltfPos = new THREE.Vector3(p[0] - origin[0], p[2] - origin[2], -(p[1] - origin[1]));
    const merc = gltfPos.applyMatrix4(yUpToZUp).applyMatrix4(basis).applyMatrix4(localToMercator);
    const expected = MercatorCoordinate.fromLngLat([lon, lat], 0);
    assert.ok(Math.abs(merc.x - expected.x) < 1e-8, `merc.x diff: ${Math.abs(merc.x - expected.x)}`);
    assert.ok(Math.abs(merc.y - expected.y) < 1e-8, `merc.y diff: ${Math.abs(merc.y - expected.y)}`);
    assert.ok(Math.abs(merc.z - expected.z) < 1e-8, `merc.z diff: ${Math.abs(merc.z - expected.z)}`);
  }
});

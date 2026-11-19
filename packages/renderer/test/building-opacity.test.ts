import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import * as THREE from 'three';
import { buildingOpacity } from '../src/page/city-timeline.js';
import { applyBuildingOpacity, setBuildingDepthPass } from '../src/page/plateau-materials.js';

describe('building opacity', () => {
  it('computes fixed, clamped, and keyframed building opacity', () => {
    assert.equal(buildingOpacity(undefined, 0), 1);
    assert.equal(buildingOpacity(0.45, 2), 0.45);
    assert.equal(buildingOpacity(-0.2, 0), 0);
    assert.equal(buildingOpacity(1.5, 0), 1);

    const keys: [number, number][] = [
      [0, 1],
      [2, 0.4],
      [4, 0.4],
    ];
    assert.equal(buildingOpacity(keys, 0), 1);
    assert.ok(Math.abs(buildingOpacity(keys, 1) - 0.7) < 1e-6);
    assert.equal(buildingOpacity(keys, 2), 0.4);
  });

  it('updates mesh materials for transparent and opaque building states while skipping ground shadows', () => {
    const buildingMat = new THREE.MeshStandardMaterial({ color: 0xffffff });
    const shadowMat = new THREE.MeshBasicMaterial({ color: 0x0a0f18, transparent: true, depthWrite: false });
    shadowMat.name = 'city-shadow';

    const root = new THREE.Group();
    root.add(new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), buildingMat));
    root.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), shadowMat));

    applyBuildingOpacity(root, 0.35);
    assert.equal(buildingMat.transparent, true);
    assert.equal(buildingMat.opacity, 0.35);
    assert.equal(buildingMat.depthWrite, false);
    assert.equal(shadowMat.opacity, 1);

    applyBuildingOpacity(root, 1);
    assert.equal(buildingMat.transparent, false);
    assert.equal(buildingMat.opacity, 1);
    assert.equal(buildingMat.depthWrite, true);
  });

  it('toggles depth pre-pass flags without affecting ground shadows in color pass', () => {
    const buildingMat = new THREE.MeshStandardMaterial({ color: 0xffffff });
    const shadowMat = new THREE.MeshBasicMaterial({ color: 0x0a0f18, transparent: true, depthWrite: false });
    shadowMat.name = 'city-shadow';

    const root = new THREE.Group();
    const buildingMesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), buildingMat);
    const shadowMesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), shadowMat);
    root.add(buildingMesh, shadowMesh);

    applyBuildingOpacity(root, 0.4);
    setBuildingDepthPass(root, true);
    assert.equal(buildingMat.colorWrite, false);
    assert.equal(buildingMat.depthWrite, true);
    assert.equal(buildingMat.transparent, false);
    assert.equal(shadowMesh.visible, false);

    setBuildingDepthPass(root, false);
    applyBuildingOpacity(root, 0.4);
    assert.equal(buildingMat.colorWrite, true);
    assert.equal(buildingMat.depthWrite, false);
    assert.equal(buildingMat.transparent, true);
    assert.equal(buildingMat.opacity, 0.4);
    assert.equal(shadowMesh.visible, true);
  });
});

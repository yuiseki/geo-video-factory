import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { applyBuildingAppearance } from '../src/page/plateau-materials.js';

test('untextured PLATEAU meshes use per-feature palette colors from the batch ID attribute', () => {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('_BATCHID', new THREE.Float32BufferAttribute([0, 1, 1], 1));
  const material = new THREE.MeshStandardMaterial({ color: 0xffffff });
  const root = new THREE.Group();
  root.add(new THREE.Mesh(geometry, material));

  const result = applyBuildingAppearance(root, ['#aa8877', '#668899'], 'ryogoku');
  assert.equal(result.patchedMaterials, 1);
  assert.equal(result.preservedTexturedMaterials, 0);
  const patched = (root.children[0] as THREE.Mesh).material as THREE.Material;
  assert.notEqual(patched, material, 'palette treatment should use a private material copy');

  const shader = {
    uniforms: {} as Record<string, unknown>,
    vertexShader: '#include <common>\nvoid main() {\n#include <begin_vertex>\n}',
    fragmentShader: '#include <common>\nvoid main() {\n#include <color_fragment>\n}',
  };
  patched.onBeforeCompile(shader as never, {} as never);
  assert.match(shader.vertexShader, /attribute float _BATCHID/);
  assert.match(shader.vertexShader, /vPlateauFeatureId/);
  assert.match(shader.fragmentShader, /uPlateauPalette/);
});

test('textured PLATEAU materials keep the original texture and do not receive a flat facade palette', () => {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('_BATCHID', new THREE.Float32BufferAttribute([0], 1));
  const texture = new THREE.Texture();
  const material = new THREE.MeshStandardMaterial({ map: texture });
  const root = new THREE.Group();
  root.add(new THREE.Mesh(geometry, material));

  const result = applyBuildingAppearance(root, ['#aa8877'], 'ryogoku');
  assert.equal(result.patchedMaterials, 0);
  assert.equal(result.preservedTexturedMaterials, 1);
  assert.equal(material.map, texture);
  assert.equal(material.onBeforeCompile, THREE.Material.prototype.onBeforeCompile);
});

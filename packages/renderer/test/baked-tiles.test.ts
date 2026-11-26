import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as THREE from 'three';
import { isBakedGltf, prepareBakedScene } from '../src/page/baked-tiles.js';
import { createCityUniforms } from '../src/page/city-materials.js';

function scene() {
  const root = new THREE.Group();
  const photo = new THREE.MeshStandardMaterial({ map: new THREE.Texture() });
  photo.name = 'photo';
  const wall = new THREE.MeshStandardMaterial({ map: new THREE.Texture(), emissiveMap: new THREE.Texture() });
  wall.name = 'pp-wall-house';
  wall.emissive.setRGB(0, 0, 0);
  const meshes = [photo, wall].map((m) => new THREE.Mesh(new THREE.BufferGeometry(), m));
  meshes.forEach((m) => root.add(m));
  return { root, photo, wall, meshes };
}

test('a GLB baked by PLATEAU++ is told apart by asset.extras.plateau_pp_bake', () => {
  assert.equal(isBakedGltf({ asset: { extras: { plateau_pp_bake: '0.1.0' } } }), true);
  assert.equal(isBakedGltf({ asset: { version: '2.0' } }), false);
  assert.equal(isBakedGltf({}), false);
});

test('a baked scene keeps its own materials and textures: no correction is applied twice', () => {
  const { root, photo, wall, meshes } = scene();
  const map = photo.map;
  prepareBakedScene(root, createCityUniforms());
  assert.equal(meshes[0]!.material, photo);
  assert.equal(meshes[1]!.material, wall);
  assert.equal(photo.map, map);
  assert.equal(photo.color.getHex(), 0xffffff);
  assert.equal(photo.onBeforeCompile.toString(), new THREE.MeshStandardMaterial().onBeforeCompile.toString());
});

test('window lights follow the scene\'s windows value, frame by frame, only on baked walls', () => {
  const { root, photo, wall, meshes } = scene();
  const city = createCityUniforms();
  prepareBakedScene(root, city);
  const draw = (mesh: THREE.Mesh) => mesh.onBeforeRender(null as never, null as never, null as never, mesh.geometry, mesh.material as THREE.Material, null as never);
  city.uCityWindows.value = 0;
  meshes.forEach(draw);
  assert.equal(wall.emissive.r, 0);
  city.uCityWindows.value = 0.8;
  meshes.forEach(draw);
  assert.ok(Math.abs(wall.emissive.r - 0.8) < 1e-9 && Math.abs(wall.emissive.b - 0.8) < 1e-9);
  assert.equal(photo.emissive.r, 0);
});

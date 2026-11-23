import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { batchUntexturedMeshes, readManifest, rowBasis, yUpToZUp } from '../src/page/plateau-buildings.js';

function meshWith(vertices: number, { textured = false, batch = true, x = 0 } = {}): THREE.Mesh {
  const g = new THREE.BufferGeometry();
  const pos = new Float32Array(vertices * 3);
  for (let i = 0; i < vertices; i++) pos.set([x + i, 0, 0], i * 3);
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  if (batch) g.setAttribute('_batchid', new THREE.BufferAttribute(new Float32Array(vertices).fill(x), 1));
  const mat = new THREE.MeshStandardMaterial();
  if (textured) mat.map = new THREE.Texture();
  return new THREE.Mesh(g, mat);
}
const meshes = (root: THREE.Object3D) => {
  const out: THREE.Mesh[] = [];
  root.traverse((o) => { if ((o as THREE.Mesh).isMesh) out.push(o as THREE.Mesh); });
  return out;
};

test('batchUntexturedMeshes merges many untextured meshes into a single draw call', () => {
  const root = new THREE.Group();
  for (let i = 0; i < 40; i++) root.add(meshWith(3, { x: i * 10 }));
  batchUntexturedMeshes(root);
  const after = meshes(root);
  assert.equal(after.length, 1);
  assert.equal(after[0]!.geometry.attributes.position!.count, 120);
  assert.equal(after[0]!.geometry.attributes._batchid!.count, 120);
});

test('batchUntexturedMeshes leaves up to 16 meshes alone (merging would not pay off)', () => {
  const root = new THREE.Group();
  for (let i = 0; i < 16; i++) root.add(meshWith(3));
  batchUntexturedMeshes(root);
  assert.equal(meshes(root).length, 16);
});

test('batchUntexturedMeshes keeps textured meshes and meshes without a batch id separate', () => {
  const root = new THREE.Group();
  for (let i = 0; i < 30; i++) root.add(meshWith(3, { x: i }));
  const textured = meshWith(3, { textured: true });
  const plain = meshWith(3, { batch: false });
  root.add(textured, plain);
  batchUntexturedMeshes(root);
  const after = meshes(root);
  assert.equal(after.length, 3);
  assert.ok(after.includes(textured) && after.includes(plain));
});

test('batchUntexturedMeshes bakes each mesh\'s world transform into the merged geometry', () => {
  const root = new THREE.Group();
  for (let i = 0; i < 20; i++) {
    const m = meshWith(1, { x: 0 });
    m.position.set(0, 100 + i, 0);
    root.add(m);
  }
  batchUntexturedMeshes(root);
  const merged = meshes(root)[0]!;
  const ys = Array.from(merged.geometry.attributes.position!.array).filter((_, i) => i % 3 === 1);
  assert.deepEqual(ys.slice(0, 3), [100, 101, 102]);
  assert.ok(merged.matrixWorld.equals(new THREE.Matrix4()));
});

test('batchUntexturedMeshes copes with an empty scene', () => {
  const root = new THREE.Group();
  batchUntexturedMeshes(root);
  assert.equal(meshes(root).length, 0);
});

test('rowBasis is a proper rotation (orthonormal, determinant +1) at any place', () => {
  for (const [lng, lat] of [[0, 0], [139.7, 35.7], [-70, -33], [10, 89]] as const) {
    const m = rowBasis(lng, lat);
    assert.ok(Math.abs(m.determinant() - 1) < 1e-9, `det at ${lng},${lat}`);
    const e = m.elements;
    const row = (r: number) => new THREE.Vector3(e[r]!, e[4 + r]!, e[8 + r]!);
    assert.ok(Math.abs(row(0).length() - 1) < 1e-9);
    assert.ok(Math.abs(row(0).dot(row(1))) < 1e-9);
    assert.ok(Math.abs(row(1).dot(row(2))) < 1e-9);
  }
});

test('rowBasis at the equator/prime meridian: east=+Y, north=+Z, up=+X in ECEF', () => {
  const m = rowBasis(0, 0);
  const apply = (v: THREE.Vector3) => v.clone().applyMatrix4(m);
  const near = (a: THREE.Vector3, b: [number, number, number]) => Math.hypot(a.x - b[0], a.y - b[1], a.z - b[2]) < 1e-9;
  assert.ok(near(apply(new THREE.Vector3(0, 1, 0)), [1, 0, 0]), 'ECEF +Y is east');
  assert.ok(near(apply(new THREE.Vector3(0, 0, 1)), [0, 1, 0]), 'ECEF +Z is north');
  assert.ok(near(apply(new THREE.Vector3(1, 0, 0)), [0, 0, 1]), 'ECEF +X is up');
});

test('yUpToZUp turns glTF Y-up into Z-up', () => {
  const m = yUpToZUp();
  const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z).applyMatrix4(m);
  assert.deepEqual(v(0, 1, 0).toArray(), [0, 0, 1]);
  assert.deepEqual(v(0, 0, 1).toArray().map((x) => x + 0), [0, -1, 0]);
  assert.deepEqual(v(1, 0, 0).toArray(), [1, 0, 0]);
});

test('readManifest validates format, tiles and HTTP status', async () => {
  const g = globalThis as Record<string, unknown>;
  const prevWindow = g.window;
  const prevFetch = g.fetch;
  g.window = { location: { origin: 'http://127.0.0.1:1' } };
  const serve = (body: unknown, status = 200) => { g.fetch = async () => new Response(JSON.stringify(body), { status }); };
  try {
    serve({ format: 'geo-video-factory.plateau-3d/1', tiles: [{ glb: 'a.glb', rtc: [0, 0, 0] }] });
    const ok = await readManifest('/p/manifest.json');
    assert.equal(ok.url.href, 'http://127.0.0.1:1/p/manifest.json');
    assert.equal(ok.manifest.tiles.length, 1);
    serve({}, 404);
    await assert.rejects(readManifest('/x.json'), /manifest 404/);
    serve({ format: 'other', tiles: [] });
    await assert.rejects(readManifest('/x.json'), /unsupported PLATEAU buildings manifest format/);
    serve({ format: 'geo-video-factory.plateau-3d/1', tiles: [] });
    await assert.rejects(readManifest('/x.json'), /has no tiles/);
  } finally {
    g.window = prevWindow;
    g.fetch = prevFetch;
  }
});

test('perf budget: batching 5000 small meshes takes under 3 s and leaves one draw call', () => {
  const root = new THREE.Group();
  for (let i = 0; i < 5000; i++) root.add(meshWith(12, { x: i }));
  const t0 = performance.now();
  batchUntexturedMeshes(root);
  const ms = performance.now() - t0;
  assert.equal(meshes(root).length, 1);
  assert.ok(ms < 3000, `${ms.toFixed(0)} ms`);
});

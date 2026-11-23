import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { populatePlateauStreetScene } from '../src/page/plateau-street-scene.js';
import { createPlateauFacadeTextureUniforms } from '../src/page/plateau-facade-glsl.js';
import { localMeters } from '../src/page/city-timeline.js';
import type { PlateauBuildingsConfig, StreetPropConfig } from '../src/types.js';

const g = globalThis as Record<string, unknown>;
const CENTER: [number, number] = [139.7, 35.66];
const saved: Record<string, unknown> = {};
const loaded: string[] = [];
let gradientColors: string[] = [];
let pixels: number[] = [];
let hasContext = true;
const loadAsync = THREE.TextureLoader.prototype.loadAsync;

beforeEach(() => {
  loaded.length = 0;
  gradientColors = [];
  pixels = new Array(16 * 16 * 4).fill(0);
  hasContext = true;
  saved.document = g.document;
  saved.window = g.window;
  g.window = { location: { origin: 'http://127.0.0.1:1' } };
  const gradient = { addColorStop: (_o: number, c: string) => { gradientColors.push(c); } };
  const ctx = {
    createRadialGradient: () => gradient,
    createLinearGradient: () => gradient,
    fillRect: () => {},
    drawImage: () => {},
    getImageData: () => ({ data: Uint8ClampedArray.from(pixels) }),
    set fillStyle(_v: unknown) {},
    set globalCompositeOperation(_v: unknown) {},
  };
  // only the 16px colour-sampling canvas can lack a 2d context; the glow textures always get one
  g.document = {
    createElement: () => {
      const canvas = { width: 0, height: 0, getContext: () => (canvas.width === 16 && !hasContext ? null : ctx) };
      return canvas;
    },
  };
  THREE.TextureLoader.prototype.loadAsync = async function (url: string) {
    loaded.push(url);
    return new THREE.Texture({ width: 16, height: 16 } as never);
  } as never;
});
afterEach(() => {
  g.document = saved.document;
  g.window = saved.window;
  THREE.TextureLoader.prototype.loadAsync = loadAsync;
});

const cfg = (extra: Partial<PlateauBuildingsConfig> = {}): PlateauBuildingsConfig => ({ manifest: 'm.json', ...extra });
const run = async (config: PlateauBuildingsConfig) => {
  const scene = new THREE.Scene();
  const uniforms = createPlateauFacadeTextureUniforms();
  await populatePlateauStreetScene(scene, config, CENTER, uniforms);
  return { scene, uniforms };
};
const bright = () => { pixels = pixels.map((_, i) => (i % 4 === 3 ? 255 : 200)); };

test('nothing configured: the scene stays empty and no texture is loaded', async () => {
  const { scene } = await run(cfg());
  assert.equal(scene.children.length, 0);
  assert.equal(loaded.length, 0);
});

test('facade textures: atlas, glass and shutter are loaded tiled and wired into the uniforms', async () => {
  const { uniforms } = await run(cfg({ facadeTextures: { atlas: 'a.png', glass: 'g.png', shutter: 's.png', wallMix: 0.6, tileMeters: [10, 20], groundZ: 12, shutterHeight: 5 } as never }));
  assert.deepEqual(loaded.map((u) => u.replace('http://127.0.0.1:1', '')), ['/a.png', '/g.png', '/s.png']);
  assert.equal(uniforms.uComfyAtlasOn.value, 1);
  assert.equal(uniforms.uComfyAtlas.value.wrapS, THREE.ClampToEdgeWrapping, 'the atlas is addressed by cell, not tiled');
  assert.equal(uniforms.uComfyGlass.value.wrapS, THREE.RepeatWrapping);
  assert.equal(uniforms.uComfyGlass.value.colorSpace, THREE.SRGBColorSpace);
  assert.equal(uniforms.uComfyGlass.value.anisotropy, 8);
  assert.equal(uniforms.uComfyWallMix.value, 0.6);
  assert.deepEqual(uniforms.uComfyTileMeters.value.toArray(), [10, 20]);
  assert.equal(uniforms.uComfyGroundZ.value, 12);
  assert.equal(uniforms.uComfyShutterHeight.value, 5);
});

test('facade textures: a lone glass or shutter texture stands in for the other; wallMix defaults to 1', async () => {
  const glassOnly = await run(cfg({ facadeTextures: { glass: 'g.png' } as never }));
  assert.equal(glassOnly.uniforms.uComfyShutter.value, glassOnly.uniforms.uComfyGlass.value);
  assert.equal(glassOnly.uniforms.uComfyWallMix.value, 1);
  assert.equal(glassOnly.uniforms.uComfyAtlasOn.value, 0);
  const shutterOnly = await run(cfg({ facadeTextures: { shutter: 's.png' } as never }));
  assert.equal(shutterOnly.uniforms.uComfyGlass.value, shutterOnly.uniforms.uComfyShutter.value);
});

test('facade textures are skipped when appearance is off (untouched PLATEAU)', async () => {
  const { uniforms } = await run(cfg({ appearance: false, facadeTextures: { atlas: 'a.png' } as never }));
  assert.equal(loaded.length, 0);
  assert.equal(uniforms.uComfyAtlasOn.value, 0);
});

const board = { src: 'b.png', center: [139.7005, 35.6605] as [number, number], altitudeM: 30, widthM: 12, heightM: 6, bearing: 90 };

test('billboard: a box sign, a halo behind it and a floor reflection in front of it', async () => {
  const { scene } = await run(cfg({ billboards: [board] }));
  assert.equal(scene.children.length, 3);
  const [sign, halo, refl] = scene.children as THREE.Mesh[];
  const [lx, ly] = localMeters(board.center, CENTER);
  assert.deepEqual(sign!.position.toArray(), [lx, ly, 30]);
  assert.equal((sign!.geometry as THREE.BoxGeometry).parameters.width, 12);
  assert.equal((sign!.geometry as THREE.BoxGeometry).parameters.height, 6);
  assert.equal(((sign!.material as THREE.Material[]).length), 6, 'frame on five faces, the picture on the front');
  assert.equal(sign!.rotation.z, ((180 - 90) * Math.PI) / 180);
  // facing east (bearing 90): the halo sits slightly behind (west of) the sign, the reflection runs east along the street
  assert.ok(halo!.position.x < lx && Math.abs(halo!.position.y - ly) < 1e-6);
  assert.ok(refl!.position.x > lx);
  assert.equal(refl!.position.z, 15 + 0.18, 'default ground height 15 m plus a hair');
  assert.equal((halo!.material as THREE.MeshBasicMaterial).blending, THREE.AdditiveBlending);
  assert.equal((halo!.material as THREE.MeshBasicMaterial).depthWrite, false);
});

test('billboard: the reflection length follows the sign height (at least 42 m) and groundZ comes from the facade config', async () => {
  const small = await run(cfg({ billboards: [board], facadeTextures: { groundZ: 3 } as never }));
  const refl = small.scene.children[2] as THREE.Mesh;
  assert.equal((refl.geometry as THREE.PlaneGeometry).parameters.height, 42);
  assert.equal(refl.position.z, 3 + 0.18);
  const tall = await run(cfg({ billboards: [{ ...board, heightM: 20 }] }));
  assert.equal(((tall.scene.children[2] as THREE.Mesh).geometry as THREE.PlaneGeometry).parameters.height, 90);
});

test('billboard glow: halo strength is capped, and the glow multiplies the picture brightness', async () => {
  bright();
  await run(cfg({ billboards: [{ ...board, glow: 5 }] }));
  assert.ok(gradientColors.some((c) => c.endsWith(',0.45)')), 'halo peak alpha capped at 0.45');
  assert.ok(gradientColors.some((c) => c.endsWith(',0.55)')), 'reflection peak alpha capped at 0.55');
  const { scene } = await run(cfg({ billboards: [{ ...board, glow: 2 }] }));
  const front = ((scene.children[0] as THREE.Mesh).material as THREE.MeshBasicMaterial[])[4]!;
  assert.deepEqual(front.color.toArray(), [2, 2, 2]);
});

test('billboard colour: the halo takes the mean colour of the picture’s bright pixels, with fallbacks', async () => {
  bright();
  await run(cfg({ billboards: [board] }));
  assert.ok(gradientColors.some((c) => c.startsWith('rgba(200,200,200,')), 'average of the bright pixels');
  gradientColors = [];
  pixels = pixels.map((_, i) => (i % 4 === 3 ? 255 : 10)); // all dark
  await run(cfg({ billboards: [board] }));
  assert.ok(gradientColors.some((c) => c.startsWith('rgba(160,175,210,')), 'dark picture: cool white');
  gradientColors = [];
  hasContext = false;
  await run(cfg({ billboards: [board] }));
  assert.ok(gradientColors.some((c) => c.startsWith('rgba(180,190,220,')), 'no 2d context: the neutral fallback colour');
});

test('ground plane: sized from its bbox in metres, raised 5 cm by default, sampled with 16x anisotropy', async () => {
  const bbox: [number, number, number, number] = [139.699, 35.659, 139.701, 35.661];
  const { scene } = await run(cfg({ groundPlane: { src: 'ground.png', bbox, brightness: 0.8 } }));
  assert.equal(scene.children.length, 1);
  const plane = scene.children[0] as THREE.Mesh;
  const [x0, y0] = localMeters([bbox[0], bbox[1]], CENTER);
  const [x1, y1] = localMeters([bbox[2], bbox[3]], CENTER);
  const { width, height } = (plane.geometry as THREE.PlaneGeometry).parameters;
  assert.ok(Math.abs(width - Math.abs(x1 - x0)) < 1e-9 && Math.abs(height - Math.abs(y1 - y0)) < 1e-9);
  assert.ok(Math.abs(plane.position.x - (x0 + x1) / 2) < 1e-9);
  assert.equal(plane.position.z, 0.05);
  const mat = plane.material as THREE.MeshBasicMaterial;
  assert.equal(mat.map!.anisotropy, 16);
  assert.equal(mat.map!.minFilter, THREE.LinearMipmapLinearFilter);
  assert.deepEqual(mat.color.toArray(), [0.8, 0.8, 0.8]);
  assert.equal(mat.toneMapped, false);
  const raised = await run(cfg({ groundPlane: { src: 'g.png', bbox, altitudeM: 2 } }));
  assert.equal((raised.scene.children[0] as THREE.Mesh).position.z, 2);
});

const prop = (kind: StreetPropConfig['kind'], extra: Partial<StreetPropConfig> = {}): StreetPropConfig => ({ kind, center: [139.7002, 35.6601], ...extra });
const group = (scene: THREE.Scene, i = 0) => scene.children[i] as THREE.Group;

test('street prop: a lamp is a pole, a bulb, a halo sprite and a light pool, placed at the right height', async () => {
  const { scene } = await run(cfg({ streetProps: [prop('lamp', { heightM: 7, altitudeM: 4 })] }));
  const lamp = group(scene);
  const [lx, ly] = localMeters([139.7002, 35.6601], CENTER);
  assert.deepEqual(lamp.position.toArray(), [lx, ly, 4]);
  assert.equal(lamp.children.length, 4);
  assert.equal(lamp.children.filter((c) => (c as THREE.Sprite).isSprite).length, 1);
  assert.equal(lamp.children.find((c) => (c as THREE.Mesh).geometry instanceof THREE.SphereGeometry)!.position.z, 7);
});

test('street prop: height defaults to 6.2 m, base height to the facade ground, bearing turns the group', async () => {
  const { scene } = await run(cfg({ facadeTextures: { groundZ: 9 } as never, streetProps: [prop('lamp', { bearing: 90 })] }));
  const lamp = group(scene);
  assert.equal(lamp.position.z, 9);
  assert.equal(lamp.rotation.z, ((180 - 90) * Math.PI) / 180);
  assert.equal(lamp.children.find((c) => (c as THREE.Mesh).geometry instanceof THREE.SphereGeometry)!.position.z, 6.2);
});

test('street prop: signal, arch, wash and kiosk each build their own non-empty group', async () => {
  const kinds: StreetPropConfig['kind'][] = ['signal', 'arch', 'wash', 'kiosk'];
  const { scene } = await run(cfg({ streetProps: kinds.map((k) => prop(k)) }));
  assert.equal(scene.children.length, 4);
  const counts = kinds.map((_, i) => group(scene, i).children.length);
  assert.deepEqual(counts, [4, 5, 7, 4], 'signal: pole, arm, box, light; arch: 2 pillars, beam, glow, floor glow; wash: strip + 6 dots; kiosk: body, roof, sign, inner light');
});

test('street prop: arch pillars straddle the span and the wash fixture hangs below its height', async () => {
  const { scene } = await run(cfg({ streetProps: [prop('arch', { widthM: 10, heightM: 5 }), prop('wash', { widthM: 12, heightM: 8 })] }));
  const pillars = group(scene, 0).children.filter((c) => (c as THREE.Mesh).geometry instanceof THREE.BoxGeometry && c.position.z === 2.5);
  assert.deepEqual(pillars.map((p) => p.position.x).sort((a, b) => a - b), [-5, 5]);
  const strip = group(scene, 1).children.find((c) => (c as THREE.Mesh).geometry instanceof THREE.PlaneGeometry)!;
  assert.equal(strip.position.z, -4);
});

test('street prop: an empty list adds nothing, and a kiosk keeps its custom colour', async () => {
  assert.equal((await run(cfg({ streetProps: [] }))).scene.children.length, 0);
  const { scene } = await run(cfg({ streetProps: [prop('kiosk', { color: '#ff0000' })] }));
  const sign = group(scene).children[2] as THREE.Mesh;
  assert.equal((sign.material as THREE.MeshBasicMaterial).color.getHexString(), 'ff0000');
});

test('perf budget: 200 street props and 50 billboards are built in under 2 s', async () => {
  const kinds: StreetPropConfig['kind'][] = ['lamp', 'signal', 'arch', 'wash', 'kiosk'];
  const streetProps = Array.from({ length: 200 }, (_, i) => prop(kinds[i % 5]!, { center: [139.7 + i * 1e-5, 35.66] }));
  const billboards = Array.from({ length: 50 }, (_, i) => ({ ...board, center: [139.7 + i * 1e-5, 35.66] as [number, number] }));
  const t0 = performance.now();
  const { scene } = await run(cfg({ streetProps, billboards }));
  const ms = performance.now() - t0;
  assert.equal(scene.children.length, 200 + 50 * 3);
  assert.ok(ms < 2000, `${ms.toFixed(0)} ms`);
});

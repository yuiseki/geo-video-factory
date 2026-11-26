// Render a trial area (out/<name>, PLATEAU++ as plateau_pp bakes it) with three.js's plain GLTFLoader in headless Chromium: no custom shader, no material touched.
//
//   node projects/2026/11/26/plateau-pp/compare_three.mjs out/<name> <out.png>
//
// Run from the repository root (three and playwright come from packages/renderer/node_modules). Placement,
// ground and camera come from out/<name>/scene.json (scene_trial.py), as in compare_blender.py; the light uses
// the same sky radiance and sun irradiance.
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';

const root = path.resolve('.');
const require = createRequire(path.join(root, 'packages/renderer/package.json'));
const { chromium } = require('playwright');
const [baked, outPng] = process.argv.slice(2).map((p) => path.resolve(p));
const scene = JSON.parse(await readFile(path.join(baked, 'scene.json'), 'utf8'));

const page_html = `<!doctype html><html><body style="margin:0">
<script type="importmap">{"imports":{"three":"http://local/packages/renderer/node_modules/three/build/three.module.js",
"three/addons/":"http://local/packages/renderer/node_modules/three/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
const scene = ${JSON.stringify(scene)};
const base = 'http://local/${path.relative(root, baked)}/';
const SKY = [0.62, 0.74, 0.9], SUN = 3.0, SUN_DIR = [-0.45, -0.55, 0.70];
const c = scene.camera;
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setSize(c.width, c.height);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.NoToneMapping;
document.body.appendChild(renderer.domElement);
const world = new THREE.Scene();
const sky = new THREE.Color().setRGB(...SKY, THREE.LinearSRGBColorSpace);
world.background = sky;
world.add(new THREE.HemisphereLight(sky, sky, Math.PI));     // uniform sky radiance L: irradiance pi L, as Blender's world
const sun = new THREE.DirectionalLight(0xffffff, SUN);
sun.position.set(...SUN_DIR);
world.add(sun);
const draco = new DRACOLoader().setDecoderPath('http://local/packages/renderer/node_modules/three/examples/jsm/libs/draco/');
const loader = new GLTFLoader().setDRACOLoader(draco);   // the photo-textured parts stay Draco-compressed, as PLATEAU serves them
for (const tile of scene.tiles) {
  const gltf = await loader.loadAsync(base + tile.glb);
  const holder = new THREE.Group();
  holder.matrixAutoUpdate = false;
  const m = tile.matrix;
  holder.matrix.set(...m[0], ...m[1], ...m[2], ...m[3]);
  const zup = new THREE.Group();
  zup.rotation.x = Math.PI / 2;            // glTF Y-up -> Z-up, as Blender's importer: (x, y, z) -> (x, -z, y)
  zup.add(gltf.scene);
  holder.add(zup);
  world.add(holder);
  console.log('loaded', tile.glb);
}
console.log('rendering', renderer.getContext().getParameter(renderer.getContext().VERSION));
const cam = new THREE.PerspectiveCamera(c.fov, c.width / c.height, 1, 20000);
cam.up.set(0, 0, 1);
cam.position.set(...c.eye);
cam.lookAt(...c.target);
renderer.render(world, cam);
window.done = true;
</script></body></html>`;

const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=gl-egl', '--ignore-gpu-blocklist'] });   // as the renderer on Linux
const page = await browser.newPage({ viewport: { width: scene.camera.width, height: scene.camera.height } });
page.on('console', (m) => console.error(m.type(), m.text()));
page.on('pageerror', (e) => console.error(e.message));
await page.route('http://local/**', async (route) => {
  const rel = decodeURIComponent(new URL(route.request().url()).pathname).slice(1);
  if (rel === 'index.html') return route.fulfill({ body: page_html, contentType: 'text/html' });
  const body = await readFile(path.join(root, rel));
  const type = rel.endsWith('.js') ? 'text/javascript' : rel.endsWith('.glb') ? 'model/gltf-binary' : rel.endsWith('.wasm') ? 'application/wasm' : 'application/octet-stream';
  return route.fulfill({ body, contentType: type });
});
await page.goto('http://local/index.html');
await page.waitForFunction(() => window.done === true, null, { timeout: 240000 });
await writeFile(outPng, await page.locator('canvas').screenshot());
await browser.close();
console.log('wrote', outPng);

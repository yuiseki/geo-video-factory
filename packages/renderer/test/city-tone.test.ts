import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import * as THREE from 'three';
import { applyCityLight, createCityLightRig, usePhotoNeutralOutput } from '../src/page/city-light-rig.js';
import { createCityProxyMaterial } from '../src/page/city-materials.js';
import { cityLight, FILL_POSITION, SUN_POSITION, upwardGain } from '../src/page/city-timeline.js';
import {
  PALETTE_WALL_GAIN, PLATEAU_PHOTO_GAMMA, PROXY_CLAY, PROXY_WALL_GAIN, STUDY_MODEL_WHITE, UNTEXTURED_BASE_MAX, UPWARD_LAMBERT,
} from '../src/page/city-tone.js';
import { applyPlateauBuildingAppearance, toStudyModelWhite } from '../src/page/plateau-materials.js';

function compile(material: THREE.Material): { uniforms: Record<string, THREE.IUniform>; vertexShader: string; fragmentShader: string } {
  const shader = {
    uniforms: {} as Record<string, THREE.IUniform>,
    vertexShader: '#include <common>\n#include <begin_vertex>',
    fragmentShader: '#include <common>\n#include <map_fragment>\n#include <color_fragment>\n#include <dithering_fragment>',
  };
  material.onBeforeCompile(shader as THREE.WebGLProgramParametersWithUniforms, {} as THREE.WebGLRenderer);
  return shader;
}

function texture(value: number): THREE.DataTexture {
  const data = new Uint8Array(4 * 4 * 4);
  for (let i = 0; i < data.length; i += 4) data.set([value, value, value, 255], i);
  const map = new THREE.DataTexture(data, 4, 4);
  map.needsUpdate = true;
  return map;
}

function building(material: THREE.MeshStandardMaterial): THREE.Mesh {
  const geometry = new THREE.BoxGeometry(10, 10, 20);
  geometry.setAttribute('_batchid', new THREE.BufferAttribute(new Float32Array(geometry.attributes.position!.count), 1));
  return new THREE.Mesh(geometry, material);
}

describe('the light on the 3D city is photo-neutral', () => {
  it('returns the albedo of an upward face, so a roof photo matches the same photo on the ground', () => {
    assert.ok(Math.abs(upwardGain(cityLight(0)) - UPWARD_LAMBERT) < 1e-9);
    assert.ok(UPWARD_LAMBERT > 0.9 && UPWARD_LAMBERT <= 1, 'the rest is the specular of the rough surface');
  });

  it('dims the roofs by as much as the aerial photo on the ground at dusk and at night', () => {
    for (const night of [0.25, 0.5, 0.75, 1]) {
      const light = cityLight(night);
      // raster-brightness-max scales display values; the light scales linear ones
      const ground = light.mapBrightness ** 2.2;
      assert.ok(Math.abs(upwardGain(light) - UPWARD_LAMBERT * ground) < 1e-9, `night ${night}`);
    }
    assert.ok(cityLight(1).fill < cityLight(0).fill * 0.4, 'the sky fill fades with the day');
  });

  it('keeps the sun where the baked ground shadows expect it, above and to the south-west', () => {
    assert.deepEqual([...SUN_POSITION], [-300, -450, 450]);
    assert.ok(FILL_POSITION[2] > 0);
  });

  it('builds the day rig from the same numbers the timeline returns for night 0', () => {
    const rig = createCityLightRig();
    const day = cityLight(0);
    assert.equal(rig.ambient.intensity, day.ambient);
    assert.equal(rig.sun.intensity, day.sun);
    assert.equal(rig.fill.intensity, day.fill);
    assert.deepEqual(rig.sun.position.toArray(), [...SUN_POSITION]);
    assert.deepEqual(rig.fill.position.toArray(), [...FILL_POSITION]);
    assert.deepEqual(rig.sun.color.toArray(), day.sunColor);
    const night = cityLight(1);
    applyCityLight(rig, night);
    assert.equal(rig.ambient.intensity, night.ambient);
    assert.deepEqual(rig.ambient.color.toArray(), night.ambientColor);
    assert.equal(rig.sun.intensity, night.sun);
    assert.equal(rig.fill.intensity, night.fill);
  });

  it('writes display colors without a film curve: tone mapping would darken the photos a second time', () => {
    const renderer = { outputColorSpace: '', toneMapping: THREE.ACESFilmicToneMapping } as unknown as THREE.WebGLRenderer;
    usePhotoNeutralOutput(renderer);
    assert.equal(renderer.toneMapping, THREE.NoToneMapping);
    assert.equal(renderer.outputColorSpace, THREE.SRGBColorSpace);
  });
});

describe('PLATEAU photo textures are brought to the tone of the aerial photo', () => {
  it('drops the base color factor and lifts the photo with a gamma curve', () => {
    const map = texture(120);
    const mesh = building(new THREE.MeshStandardMaterial({ color: new THREE.Color(0.7, 0.7, 0.7), map }));
    const root = new THREE.Group();
    root.add(mesh);
    applyPlateauBuildingAppearance(root, { palette: [null], seed: 1 });
    const updated = mesh.material as THREE.MeshStandardMaterial;
    assert.deepEqual(updated.color.toArray(), [1, 1, 1], 'a 0.7 factor multiplied the photo once more');
    assert.ok(PLATEAU_PHOTO_GAMMA > 0.5 && PLATEAU_PHOTO_GAMMA < 0.7);
    const shader = compile(updated);
    const curve = `diffuseColor.rgb = diffuse * pow(max(sampledDiffuseColor.rgb, vec3(0.0)), vec3(${PLATEAU_PHOTO_GAMMA.toFixed(3)}));`;
    assert.ok(shader.fragmentShader.includes(`#include <map_fragment>\n${curve}`), shader.fragmentShader.slice(0, 400));
  });

  it('still tones down a washed-out atlas, outside the curve', () => {
    const mesh = building(new THREE.MeshStandardMaterial({ color: new THREE.Color(0.7, 0.7, 0.7), map: texture(235) }));
    const root = new THREE.Group();
    root.add(mesh);
    applyPlateauBuildingAppearance(root, { seed: 1 });
    const updated = mesh.material as THREE.MeshStandardMaterial;
    assert.ok(Math.abs(updated.color.r - 0.64) < 1e-6);
  });

  it('leaves untextured buildings without the curve and uses a new shader program', () => {
    const plain = building(new THREE.MeshStandardMaterial({ color: 0xffffff }));
    const photo = building(new THREE.MeshStandardMaterial({ map: texture(120) }));
    const root = new THREE.Group();
    root.add(plain, photo);
    applyPlateauBuildingAppearance(root, { palette: ['#c8c2b6'], seed: 3 });
    const plainMaterial = plain.material as THREE.MeshStandardMaterial;
    assert.doesNotMatch(compile(plainMaterial).fragmentShader, /sampledDiffuseColor/);
    assert.match(plainMaterial.customProgramCacheKey(), /^plateau-facade-v4-/);
    assert.match((photo.material as THREE.MeshStandardMaterial).customProgramCacheKey(), /^plateau-facade-v4-/);
  });
});

describe('estimated walls sit in the tonal range of photographed walls', () => {
  it('darkens the palette color of untextured PLATEAU buildings', () => {
    const mesh = building(new THREE.MeshStandardMaterial({ color: 0xffffff }));
    const root = new THREE.Group();
    root.add(mesh);
    applyPlateauBuildingAppearance(root, { palette: ['#c8c2b6'], seed: 3 });
    const updated = mesh.material as THREE.MeshStandardMaterial;
    assert.ok(PALETTE_WALL_GAIN > 0.5 && PALETTE_WALL_GAIN < 0.75);
    assert.ok(compile(updated).fragmentShader.includes(`diffuseColor.rgb = plateauSample.rgb * ${PALETTE_WALL_GAIN.toFixed(3)};`));
    assert.ok(Math.max(...updated.color.toArray()) <= UNTEXTURED_BASE_MAX + 1e-6, 'buildings without a palette color follow');
    assert.ok(Math.abs(UNTEXTURED_BASE_MAX - 0.45 * PALETTE_WALL_GAIN) < 0.005);
  });

  it('darkens the walls of city-proxy buildings and leaves their roofs to the photo', () => {
    const material = createCityProxyMaterial({ texture: new THREE.Texture(), bounds: [0, 0, 1, 1] });
    const shader = compile(material);
    assert.ok(PROXY_WALL_GAIN > 0.35 && PROXY_WALL_GAIN < 0.6);
    assert.ok(shader.fragmentShader.includes(
      `vec3 cityPainted = diffuseColor.rgb * mix(${PROXY_WALL_GAIN.toFixed(3)}, 1.0, step(0.35, abs(vCityUp)));`));
    assert.match(material.customProgramCacheKey(), /^city-proxy-v7/);
  });
});

describe('unpainted study models keep the look they had under the film curve', () => {
  it('uses whites below 1, which the neutral light would clip on every roof', () => {
    assert.ok(STUDY_MODEL_WHITE > 0.5 && STUDY_MODEL_WHITE < 0.65);
    assert.ok(Math.max(...PROXY_CLAY) < 0.55 && PROXY_CLAY[2] < PROXY_CLAY[0], 'a slightly warm clay');
    const shader = compile(createCityProxyMaterial());
    const clay = PROXY_CLAY.map((value) => value.toFixed(3)).join(', ');
    assert.ok(shader.fragmentShader.includes(`diffuseColor.rgb = mix(vec3(${clay}), cityPainted, vCityPaint);`));
  });

  it('brings the white of every untextured PLATEAU material to the study model white, once', () => {
    const white = new THREE.MeshStandardMaterial({ color: 0xffffff });
    toStudyModelWhite(white);
    toStudyModelWhite(white);
    assert.ok(Math.abs(white.color.r - STUDY_MODEL_WHITE) < 1e-6, 'a material shared by several meshes is dimmed once');
    const gray = new THREE.MeshStandardMaterial({ color: new THREE.Color().setRGB(0.5, 0.4, 0.3) });
    toStudyModelWhite(gray);
    assert.ok(Math.abs(gray.color.g - 0.4 * STUDY_MODEL_WHITE) < 1e-6, 'a colored material keeps its hue');
    const photo = new THREE.MeshStandardMaterial({ color: 0xffffff, map: texture(128) });
    toStudyModelWhite(photo);
    assert.equal(photo.color.r, 1, 'photo textures are left alone');
    const basic = new THREE.MeshBasicMaterial({ color: 0xffffff });
    toStudyModelWhite(basic);
    assert.equal(basic.color.r, 1);
  });

  it('shows the dimmed white before the paint wave and paints the same wall after it', () => {
    const material = new THREE.MeshStandardMaterial({ color: 0xffffff });
    toStudyModelWhite(material);
    const mesh = building(material);
    const root = new THREE.Group();
    root.add(mesh);
    applyPlateauBuildingAppearance(root, { palette: ['#c8c0b4'] });
    const shader = compile(mesh.material as THREE.Material);
    const raw = shader.uniforms.uPlateauRawColor!.value as THREE.Color;
    assert.ok(Math.abs(raw.r - STUDY_MODEL_WHITE) < 1e-6);
  });
});

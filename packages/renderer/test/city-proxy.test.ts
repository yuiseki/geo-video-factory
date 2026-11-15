import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import * as THREE from 'three';
import { cityLight, keyframeValue, localMeters, revealProgress } from '../src/page/city-timeline.js';
import { cityUniforms, createCityProxyMaterial } from '../src/page/city-materials.js';
import { buildMapStyle } from '../src/page/map-style.js';
import { tileHeightOffset } from '../src/page/plateau-coordinates.js';
import type { ShotSpec } from '../src/types.js';

describe('city timeline', () => {
  it('interpolates keyframes linearly and holds the ends', () => {
    const keys: [number, number][] = [[10, 0], [20, 1], [30, 0.5]];
    assert.equal(keyframeValue(keys, 0), 0);
    assert.equal(keyframeValue(keys, 15), 0.5);
    assert.equal(keyframeValue(keys, 25), 0.75);
    assert.equal(keyframeValue(keys, 99), 0.5);
    assert.equal(keyframeValue(undefined, 5), 0);
    assert.equal(keyframeValue([], 5), 0);
  });

  it('grows buildings outward from the reveal center as time passes', () => {
    const reveal = { center: [139.31, 35.75] as [number, number], radius: [[2, -50], [6, 350]] as [number, number][], width: 50 };
    assert.equal(revealProgress(reveal, 1, 0), 0, 'nothing before the start');
    assert.equal(revealProgress(reveal, 3, 0), 1, 'the center is fully up after the front passes');
    assert.equal(revealProgress(reveal, 3, 400), 0, 'far buildings wait for the front');
    const half = revealProgress(reveal, 3, 25);
    assert.ok(half > 0 && half < 1);
    assert.equal(revealProgress(undefined, 0, 1000), 1, 'no reveal means everything stands');
    const rewind = { center: [139.31, 35.75] as [number, number], radius: [[0, 5000], [1, -200]] as [number, number][] };
    assert.equal(revealProgress(rewind, 0, 300), 1);
    assert.equal(revealProgress(rewind, 1, 0), 0, 'a shrinking front sinks the buildings again');
    const [east, north] = localMeters([139.32, 35.76], [139.31, 35.75]);
    assert.ok(Math.abs(east - 903.5) < 1 && Math.abs(north - 1109.5) < 0.1);
  });

  it('turns daylight into dusk and night', () => {
    const day = cityLight(0);
    const dusk = cityLight(0.5);
    const night = cityLight(1);
    assert.equal(day.windows, 0);
    assert.ok(night.windows > 0.9);
    assert.ok(night.sun < day.sun * 0.3);
    assert.ok(dusk.sunColor[0] > dusk.sunColor[2], 'dusk light is warm');
    assert.ok(night.mapBrightness < 0.4 && day.mapBrightness === 1);
    assert.ok(day.shadow > 0.3 && night.shadow === 0, 'shadows fade out at night');
  });
});

describe('city proxy material', () => {
  it('uses vertex colors and one shader program for every building, driven by shared uniforms', () => {
    const a = createCityProxyMaterial();
    const b = createCityProxyMaterial();
    assert.equal(a.vertexColors, true);
    assert.equal(a.customProgramCacheKey(), b.customProgramCacheKey());
    const shader = {
      uniforms: {} as Record<string, THREE.IUniform>,
      vertexShader: '#include <common>\n#include <begin_vertex>',
      fragmentShader: '#include <common>\n#include <dithering_fragment>',
    };
    a.onBeforeCompile(shader as THREE.WebGLProgramParametersWithUniforms, {} as THREE.WebGLRenderer);
    assert.match(shader.vertexShader, /attribute vec2 _style/);
    assert.match(shader.vertexShader, /cityGrow/);
    assert.match(shader.fragmentShader, /cityWindow/);
    assert.equal(shader.uniforms.uCityNight, cityUniforms.uCityNight, 'uniforms are shared, not copied');
  });

  it('places proxy tiles at map altitude', () => {
    assert.equal(tileHeightOffset('city-proxy', -39), 0);
    assert.equal(tileHeightOffset('city-shadow', -39), 0);
    assert.equal(tileHeightOffset(undefined, -39), -39);
  });
});

describe('terrain under buildings', () => {
  const base: ShotSpec = { shots: [{ duration: 1, from: { center: [139, 35], zoom: 15 }, to: { center: [139, 35], zoom: 15 } }] } as ShotSpec;

  it('keeps terrain at true scale when 3D buildings are shown, so they are not buried', () => {
    const withBuildings = buildMapStyle({ ...base, plateauBuildings: { manifest: 'm.json' } }) as { terrain: { exaggeration: number } };
    assert.equal(withBuildings.terrain.exaggeration, 1);
    const plain = buildMapStyle(base) as { terrain: { exaggeration: number } };
    assert.equal(plain.terrain.exaggeration, 1.3);
  });
});

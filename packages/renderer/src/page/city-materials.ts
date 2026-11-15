import * as THREE from 'three';
import { CITY_FACADE } from './city-facade-glsl.js';

/**
 * Uniforms shared by the city materials of one scene (one manifest), updated once per frame.
 * Grow: buildings within uCityGrowRadius - uCityGrowWidth (meters, world plane) of
 * uCityGrowOrigin stand; beyond uCityGrowRadius they are flat. Paint works the same way for the
 * second wave. Windows: 0 none lit .. 1 night.
 */
export function createCityUniforms() {
  return {
    uCityGrowOrigin: { value: new THREE.Vector2(0, 0) },
    uCityGrowRadius: { value: 1e9 },
    uCityGrowWidth: { value: 120 },
    uCityPaintRadius: { value: 1e9 },
    uCityWindows: { value: 0 },
    uCityNight: { value: 0 },
    uCityShadow: { value: 0.38 },
  };
}

export type CityUniforms = ReturnType<typeof createCityUniforms>;

/** The default set, for materials created without a scene of their own. */
export const cityUniforms = createCityUniforms();

/**
 * Ground shadows of `city-shadow` tiles: a flat dark veil whose opacity follows the light and
 * which only appears where the buildings have risen.
 */
export function createCityShadowMaterial(uniforms: CityUniforms = cityUniforms): THREE.MeshBasicMaterial {
  const material = new THREE.MeshBasicMaterial({
    color: 0x0a0f18, transparent: true, depthWrite: false, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
  });
  material.customProgramCacheKey = () => 'city-shadow-v1';
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', `#include <common>
uniform vec2 uCityGrowOrigin;
uniform float uCityGrowRadius;
uniform float uCityGrowWidth;
varying float vShadowGrow;`)
      .replace('#include <begin_vertex>', `#include <begin_vertex>
vec4 shadowWorld = modelMatrix * vec4(transformed, 1.0);
vShadowGrow = clamp((uCityGrowRadius - distance(shadowWorld.xy, uCityGrowOrigin)) / uCityGrowWidth, 0.0, 1.0);`);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>
uniform float uCityShadow;
varying float vShadowGrow;`)
      .replace('#include <dithering_fragment>', `gl_FragColor.a = uCityShadow * vShadowGrow * vShadowGrow;
#include <dithering_fragment>`);
  };
  return material;
}

/**
 * Material for `city-proxy` tiles (see packages/pipeline/city_proxy.py). Expects vertex colors,
 * uv = (meters along the wall, meters above the building's ground), _style = (style, eave height)
 * and _batchid, in a Y-up local frame. Windows are a deterministic illustration per building.
 */
export interface CityRoofPhoto {
  texture: THREE.Texture;
  /** [minEast, minNorth, maxEast, maxNorth] of the photo in the tile's local meters. */
  bounds: [number, number, number, number];
}

export function createCityProxyMaterial(roof?: CityRoofPhoto, uniforms: CityUniforms = cityUniforms): THREE.MeshStandardMaterial {
  const material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.88, metalness: 0, side: THREE.DoubleSide });
  material.customProgramCacheKey = () => `city-proxy-v6${roof ? '-roof' : ''}`;
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    if (roof) {
      const [x0, y0, x1, y1] = roof.bounds;
      shader.uniforms.uCityRoofPhoto = { value: roof.texture };
      shader.uniforms.uCityRoofMin = { value: new THREE.Vector2(x0, y0) };
      shader.uniforms.uCityRoofSize = { value: new THREE.Vector2(x1 - x0, y1 - y0) };
      shader.fragmentShader = '#define CITY_ROOF_PHOTO\n' + shader.fragmentShader;
    }
    shader.vertexShader = shader.vertexShader
      .replace(
        '#include <common>',
        `#include <common>
attribute vec2 _style;
attribute float _batchid;
uniform vec2 uCityGrowOrigin;
uniform float uCityGrowRadius;
uniform float uCityGrowWidth;
uniform float uCityPaintRadius;
varying vec2 vCityUv;
varying vec2 vCityStyle;
varying float vCityBatch;
varying float vCityUp;
varying float vCityPaint;
varying vec2 vCityWorld;`,
      )
      .replace(
        '#include <begin_vertex>',
        `#include <begin_vertex>
vec4 cityWorld = modelMatrix * vec4(transformed, 1.0);
float cityDist = distance(cityWorld.xy, uCityGrowOrigin);
float cityG = clamp((uCityGrowRadius - cityDist) / uCityGrowWidth, 0.0, 1.0);
float cityGrow = 1.0 - pow(1.0 - cityG, 3.0);
transformed.y -= uv.y * (1.0 - cityGrow);
vCityUv = uv;
vCityStyle = _style;
vCityBatch = _batchid;
vCityUp = normal.y;
vCityPaint = clamp((uCityPaintRadius - cityDist) / uCityGrowWidth, 0.0, 1.0);
vCityWorld = cityWorld.xy;`,
      );
    shader.fragmentShader = shader.fragmentShader
      .replace(
        '#include <common>',
        `#include <common>
uniform float uCityWindows;
uniform float uCityNight;
varying vec2 vCityUv;
varying vec2 vCityStyle;
varying float vCityBatch;
varying float vCityUp;
varying float vCityPaint;
varying vec2 vCityWorld;
#ifdef CITY_ROOF_PHOTO
uniform sampler2D uCityRoofPhoto;
uniform vec2 uCityRoofMin;
uniform vec2 uCityRoofSize;
#endif
float cityHash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}`,
      )
      .replace(
        '#include <color_fragment>',
        `#include <color_fragment>
vec3 cityPainted = diffuseColor.rgb;
#ifdef CITY_ROOF_PHOTO
// Roofs show the aerial photo itself: from above, a roof is what the photo shows.
float cityRoofFace = step(0.35, abs(vCityUp));
vec3 cityPhoto = texture2D(uCityRoofPhoto, (vCityWorld - uCityRoofMin) / uCityRoofSize).rgb;
cityPainted = mix(cityPainted, cityPhoto, cityRoofFace);
#endif
// Before the paint wave arrives the building is a clay-white study model.
diffuseColor.rgb = mix(vec3(0.80, 0.80, 0.78), cityPainted, vCityPaint);`,
      )
      .replace(
        '#include <dithering_fragment>',
        `gl_FragColor.rgb = mix(gl_FragColor.rgb * 0.45 + vec3(0.52), gl_FragColor.rgb, vCityPaint);
${CITY_FACADE}#include <dithering_fragment>`,
      );
  };
  material.needsUpdate = true;
  return material;
}

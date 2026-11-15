import * as THREE from 'three';

/**
 * Uniforms shared by every city material, updated once per frame by the buildings layer.
 * Grow: buildings within uCityGrowRadius - uCityGrowWidth (meters, world plane) of
 * uCityGrowOrigin stand; beyond uCityGrowRadius they are flat. Windows: 0 none lit .. 1 night.
 */
export const cityUniforms = {
  uCityGrowOrigin: { value: new THREE.Vector2(0, 0) },
  uCityGrowRadius: { value: 1e9 },
  uCityGrowWidth: { value: 120 },
  uCityPaintRadius: { value: 1e9 },
  uCityWindows: { value: 0 },
  uCityNight: { value: 0 },
  uCityShadow: { value: 0.38 },
};

/**
 * Ground shadows of `city-shadow` tiles: a flat dark veil whose opacity follows the light and
 * which only appears where the buildings have risen.
 */
export function createCityShadowMaterial(): THREE.MeshBasicMaterial {
  const material = new THREE.MeshBasicMaterial({
    color: 0x0a0f18, transparent: true, depthWrite: false, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
  });
  material.customProgramCacheKey = () => 'city-shadow-v1';
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, cityUniforms);
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

export function createCityProxyMaterial(roof?: CityRoofPhoto): THREE.MeshStandardMaterial {
  const material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.88, metalness: 0, side: THREE.DoubleSide });
  material.customProgramCacheKey = () => `city-proxy-v5${roof ? '-roof' : ''}`;
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, cityUniforms);
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
float cityWall = 1.0 - step(0.35, abs(vCityUp));
float cityStyle = floor(vCityStyle.x + 0.5);
float cityHouse = 1.0 - step(0.5, cityStyle);
float cityEave = vCityStyle.y;
float cityR = cityHash(vec2(vCityBatch, 3.7));
float cityStorey = cityStyle > 0.5 ? 3.25 : 2.85;
float cityBay = cityStyle > 0.5 ? 2.6 + cityR * 0.8 : 3.3 + cityR * 1.3;
float cityFy = vCityUv.y / cityStorey;
float cityFx = vCityUv.x / cityBay;
vec2 cityCellId = vec2(floor(cityFx) + vCityBatch * 7.13, floor(cityFy) + vCityBatch * 1.37);
float cityWx = fract(cityFx);
float cityWy = fract(cityFy);
// Windows are rectangles on a regular grid: one row per storey, one column per bay. Whether a
// bay has windows is decided per column, so a column is either glazed from bottom to top or not.
float cityColumn = cityHash(vec2(floor(cityFx), vCityBatch * 0.731 + 11.0));
float cityPresent = step(cityStyle > 0.5 ? 0.0 : 0.35, cityColumn) * (1.0 - step(1.5, cityStyle));
float cityHalf = cityStyle > 0.5 ? 0.34 : 0.22;
float cityAaX = max(fwidth(cityFx), 1e-4);
float cityAaY = max(fwidth(cityFy), 1e-4);
float cityInX = smoothstep(0.5 - cityHalf - cityAaX, 0.5 - cityHalf + cityAaX, cityWx) * (1.0 - smoothstep(0.5 + cityHalf - cityAaX, 0.5 + cityHalf + cityAaX, cityWx));
float cityInY = smoothstep(0.32 - cityAaY, 0.32 + cityAaY, cityWy) * (1.0 - smoothstep(0.82 - cityAaY, 0.82 + cityAaY, cityWy));
float cityBelow = step(0.7, vCityUv.y) * step(vCityUv.y, cityEave - 0.45);
float cityWindow = cityWall * cityPresent * cityInX * cityInY * cityBelow * vCityPaint;
// Prefilter: when a storey covers only a few pixels, use the average window coverage instead of
// the pattern, so distant walls do not shimmer as black speckles.
float cityPx = max(fwidth(vCityUv.x), fwidth(vCityUv.y));
float cityDetail = 1.0 - smoothstep(0.18, 0.45, cityPx / cityStorey);
float cityCoverage = vCityPaint * cityWall * cityBelow * (1.0 - step(1.5, cityStyle)) * (cityStyle > 0.5 ? 0.68 : 0.65 * 0.44) * 0.5;
float cityGlassMix = mix(cityCoverage, cityWindow, cityDetail);
vec3 cityGlass = mix(vec3(0.20, 0.24, 0.29), vec3(0.42, 0.48, 0.56), cityHash(cityCellId + 9.1));
gl_FragColor.rgb = mix(gl_FragColor.rgb, mix(vec3(0.27, 0.31, 0.37), cityGlass, cityDetail), cityGlassMix * 0.72);
float cityBand = cityWall * (1.0 - step(1.5, cityStyle)) * (1.0 - smoothstep(0.0, 0.05, min(cityWy, 1.0 - cityWy))) * step(1.0, vCityUv.y) * cityDetail * vCityPaint;
gl_FragColor.rgb *= 1.0 - cityBand * 0.08;
// No wall stays flat: houses get lap siding, wall-less sheds get vertical slats.
float citySiding = cityWall * cityHouse * (1.0 - smoothstep(0.0, 0.12, fract(vCityUv.y / 0.42))) * cityDetail * vCityPaint;
gl_FragColor.rgb *= 1.0 - citySiding * 0.10;
float citySlat = cityWall * step(1.5, cityStyle) * (1.0 - smoothstep(0.0, 0.25, fract(vCityUv.x / 0.55))) * cityDetail * vCityPaint;
gl_FragColor.rgb *= 1.0 - citySlat * 0.22;
gl_FragColor.rgb *= mix(1.0, mix(0.72, 1.0, smoothstep(0.2, 2.4, vCityUv.y)), cityWall);
float cityLitShare = uCityWindows * (0.45 + 0.4 * cityR);
float cityLit = step(1.0 - cityLitShare, cityHash(cityCellId + 4.2));
vec3 cityWarm = mix(vec3(1.0, 0.72, 0.40), vec3(0.85, 0.92, 1.0), step(0.85, cityHash(cityCellId + 2.3)));
vec3 cityWarmAvg = mix(vec3(1.0, 0.72, 0.40), vec3(0.85, 0.92, 1.0), 0.15);
vec3 cityGlow = mix(cityWarmAvg * cityCoverage * cityLitShare * 0.9, cityWarm * cityWindow * cityLit, cityDetail);
gl_FragColor.rgb = mix(gl_FragColor.rgb, gl_FragColor.rgb * vec3(0.90, 0.93, 1.02), uCityNight);
gl_FragColor.rgb += cityGlow * uCityWindows * 1.2;
#include <dithering_fragment>`,
      );
  };
  material.needsUpdate = true;
  return material;
}

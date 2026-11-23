/**
 * GLSL for the walls of untextured PLATEAU buildings, spliced into the facade shader of
 * plateau-materials.ts (it uses that shader's facadeWall, facadeAxis, buildingRnd, plateauTall...).
 * Tall buildings get a curtain wall, low ones a house facade. Estimates for the picture.
 */
import * as THREE from "three";

const blankTexture = new THREE.DataTexture(new Uint8Array([128, 128, 128, 255]), 1, 1, THREE.RGBAFormat);
blankTexture.needsUpdate = true;

/**
 * Aerial photo draped on the roofs of untextured PLATEAU buildings (enhanced render only).
 * Set once per scene from the manifest's roof_texture; off (0) by default.
 */
export function createPlateauRoofUniforms() {
  return {
    uPlateauRoofPhoto: { value: blankTexture as THREE.Texture },
    uPlateauRoofMin: { value: new THREE.Vector2(0, 0) },
    uPlateauRoofSize: { value: new THREE.Vector2(1, 1) },
    uPlateauRoofOn: { value: 0 },
  };
}

export type PlateauRoofUniforms = ReturnType<typeof createPlateauRoofUniforms>;

/** The default set, for materials created without a scene of their own. */
export const plateauRoofUniforms = createPlateauRoofUniforms();

/** Optional ComfyUI/custom tileable facade textures mapped onto building walls in meters. */
export function createPlateauFacadeTextureUniforms() {
  return {
    uComfyGlass: { value: blankTexture as THREE.Texture },
    uComfyShutter: { value: blankTexture as THREE.Texture },
    uComfyAtlas: { value: blankTexture as THREE.Texture },
    uComfyAtlasOn: { value: 0 },
    uComfyWallMix: { value: 0 },
    uComfyTileMeters: { value: new THREE.Vector2(14, 14) },
    uComfyGroundZ: { value: 0 },
    uComfyShutterHeight: { value: 4.5 },
  };
}

export type PlateauFacadeTextureUniforms = ReturnType<typeof createPlateauFacadeTextureUniforms>;

export const plateauFacadeTextureUniforms = createPlateauFacadeTextureUniforms();

export function resolveIdVariants(
  ids: string[] | undefined,
  idVariants: Record<string, number> | undefined,
): Array<number | null> | undefined {
  if (!idVariants || !ids?.length) return undefined;
  return ids.map((id) => (idVariants[id] !== undefined ? idVariants[id]! : null));
}

function parseHexBytes(hex: string | null | undefined): [number, number, number, number] | null {
  if (!hex || !/^#[0-9a-f]{6}([0-9a-f]{2})?$/i.test(hex)) return null;
  return [
    Number.parseInt(hex.slice(1, 3), 16),
    Number.parseInt(hex.slice(3, 5), 16),
    Number.parseInt(hex.slice(5, 7), 16),
    hex.length === 9 ? Number.parseInt(hex.slice(7, 9), 16) : 255,
  ];
}

export function paletteTexture(palette: Array<string | null>): THREE.DataTexture {
  const count = Math.max(1, palette.length);
  const data = new Uint8Array(count * 4);
  for (let i = 0; i < count; i++) {
    const rgb = parseHexBytes(palette[i]);
    if (rgb) {
      data[i * 4] = rgb[0];
      data[i * 4 + 1] = rgb[1];
      data[i * 4 + 2] = rgb[2];
      data[i * 4 + 3] = rgb[3];
    } else {
      data[i * 4] = 177;
      data[i * 4 + 1] = 177;
      data[i * 4 + 2] = 177;
      data[i * 4 + 3] = 0;
    }
  }
  const texture = new THREE.DataTexture(data, count, 1, THREE.RGBAFormat);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.magFilter = THREE.NearestFilter;
  texture.minFilter = THREE.NearestFilter;
  texture.needsUpdate = true;
  return texture;
}

export function variantTexture(variants: Array<number | null>): THREE.DataTexture {
  const count = Math.max(1, variants.length);
  const data = new Uint8Array(count * 4);
  for (let i = 0; i < count; i++) {
    const v = variants[i];
    if (v !== null && v !== undefined && Number.isFinite(v)) {
      data[i * 4] = Math.max(0, Math.min(255, Math.round(v)));
      data[i * 4 + 3] = 255;
    }
  }
  const texture = new THREE.DataTexture(data, count, 1, THREE.RGBAFormat);
  texture.magFilter = THREE.NearestFilter;
  texture.minFilter = THREE.NearestFilter;
  texture.needsUpdate = true;
  return texture;
}

export function applyWetGroundShader(material: THREE.MeshBasicMaterial): void {
  material.customProgramCacheKey = () => "wet-ground-v1";
  material.onBeforeCompile = (shader) => {
    shader.fragmentShader = shader.fragmentShader.replace(
      "#include <map_fragment>",
      `#include <map_fragment>
float wetLuma = dot(diffuseColor.rgb, vec3(0.299, 0.587, 0.114));
float wetPuddleMask = 1.0 - smoothstep(0.08, 0.34, wetLuma);
float wetZebraMask = smoothstep(0.38, 0.68, wetLuma);
vec3 wetChroma = diffuseColor.rgb - vec3(wetLuma);
diffuseColor.rgb = mix(diffuseColor.rgb * 0.86 + wetChroma * 0.75, diffuseColor.rgb * 1.16, wetZebraMask);
diffuseColor.rgb += max(wetChroma, vec3(0.0)) * wetPuddleMask * 0.55;`,
    );
  };
  material.needsUpdate = true;
}

export function comfyFacadeMapGlsl(variantSize: number): string {
  const variantLookup = variantSize > 0
    ? `float vIdx = clamp(floor(vPlateauFeatureId + 0.5), 0.0, uComfyVariantSize - 1.0);
    vec4 vSample = texture2D(uComfyVariantMap, vec2((vIdx + 0.5) / uComfyVariantSize, 0.5));
    if (vSample.a > 0.5) {
      cVar = floor(vSample.r * 255.0 + 0.5);
    }`
    : "";
  return `if (uComfyWallMix > 0.001) {
  vec3 cfn = normalize(vPlateauWorldNormal);
  float cWall = smoothstep(0.58, 0.90, 1.0 - abs(cfn.z));
  float cAxis = abs(cfn.x) > abs(cfn.y) ? vPlateauWorldPos.y : vPlateauWorldPos.x;
  vec2 cUv = vec2(cAxis / uComfyTileMeters.x, (vPlateauWorldPos.z - uComfyGroundZ) / uComfyTileMeters.y);
  vec3 cFacadeTex;
  if (uComfyAtlasOn > 0.5) {
    float cVar = mod(floor(vPlateauFeatureId + 0.5 + uPlateauSeed * 7.0), 6.0);
    ${variantLookup}
    vec2 cCell = vec2(mod(cVar, 3.0), 1.0 - floor(cVar / 3.0));
    vec2 cLocal = vec2(fract(cUv.x), fract(cUv.y));
    cFacadeTex = texture2D(uComfyAtlas, (cCell + cLocal) / vec2(3.0, 2.0)).rgb;
  } else {
    vec3 cGlass = texture2D(uComfyGlass, cUv).rgb;
    vec3 cShutter = texture2D(uComfyShutter, cUv).rgb;
    float cIsGround = 1.0 - smoothstep(uComfyShutterHeight - 0.6, uComfyShutterHeight + 0.6, vPlateauWorldPos.z - uComfyGroundZ);
    cFacadeTex = mix(cGlass, cShutter, cIsGround);
  }
  float cDirShade = 0.85 + 0.22 * clamp(dot(normalize(cfn.xy + 1e-5), normalize(vec2(-0.5, -0.8))), -1.0, 1.0);
  float cGroundAo = mix(0.76, 1.0, smoothstep(0.0, 3.2, max(0.0, vPlateauWorldPos.z - uComfyGroundZ)));
  cFacadeTex = min(vec3(1.0), cFacadeTex * 1.65) * cDirShade * cGroundAo;
  diffuseColor.rgb = mix(diffuseColor.rgb, cFacadeTex, cWall * uComfyWallMix);
}`;
}

export const COMFY_WINDOW_GLOW = `if (uComfyWallMix > 0.001) {
  float cSparseLit = step(1.0 - uCityWindows * 0.28, plateauHash(facadeCell + 7.9));
  vec3 cWinCol = mix(vec3(1.0, 0.78, 0.48), vec3(0.72, 0.88, 1.0), step(0.6, plateauHash(facadeCell + 1.9)));
  vec3 cComfyWindowGlow = cWinCol * facadeWall * facadeWindow * cSparseLit * uCityWindows * uComfyWallMix * 0.38;
  gl_FragColor.rgb += cComfyWindowGlow;
  gl_FragColor.rgb *= 1.0 - facadeWall * facadeBand * uComfyWallMix * 0.12;
}
`;

// Curtain wall for untextured walls: storeys, mullions, glass reflecting the sky, floor slabs.
// An estimate for the picture, never a survey of the real facade.
export const UNTEXTURED_FACADE = `float curtainWall = facadeWall * plateauTall * vPlateauPaint;
float houseWall = facadeWall * (1.0 - plateauTall) * vPlateauPaint;
float curtainStorey = 3.7 + buildingRnd * 0.5;
float curtainMull = 1.35 + buildingRnd2 * 0.7;
float cfy = vPlateauWorldPos.z / curtainStorey;
float cfx = facadeAxis / curtainMull;
float caax = max(fwidth(cfx), 1e-4);
float caay = max(fwidth(cfy), 1e-4);
float cwx = fract(cfx);
float cwy = fract(cfy);
float cgx = smoothstep(0.07 - caax, 0.07 + caax, cwx) * (1.0 - smoothstep(0.93 - caax, 0.93 + caax, cwx));
float cgy = smoothstep(0.24 - caay, 0.24 + caay, cwy) * (1.0 - smoothstep(0.93 - caay, 0.93 + caay, cwy));
float cdetail = 1.0 - smoothstep(0.25, 0.6, max(caax, caay));
float curtainGlass = curtainWall * mix(0.86 * 0.69, cgx * cgy, cdetail);
float cpanel = plateauHash(vec2(floor(cfx), floor(cfy)) + vPlateauFeatureId * 0.37);
float cheight = clamp(vPlateauWorldPos.z / 220.0, 0.0, 1.0);
vec3 csky = mix(vec3(0.33, 0.40, 0.48), vec3(0.66, 0.73, 0.80), 0.25 + 0.55 * cheight);
csky = mix(csky, vec3(0.20, 0.24, 0.27), step(0.55, buildingRnd2) * 0.45);
float csun = max(dot(normalize(facadeN.xy + 1e-5), vec2(-0.55, -0.83)), 0.0);
vec3 cglass = csky * (0.86 + 0.20 * cpanel) * (0.72 + 0.28 * csun);
gl_FragColor.rgb = mix(gl_FragColor.rgb, cglass, curtainGlass * 0.9);
float cslab = curtainWall * (1.0 - smoothstep(0.0, 0.06, min(cwy, 1.0 - cwy))) * cdetail;
gl_FragColor.rgb *= 1.0 - cslab * 0.18;
float clit = step(1.0 - uCityWindows * 0.7, cpanel);
gl_FragColor.rgb += vec3(1.0, 0.78, 0.5) * curtainGlass * clit * uCityWindows;
// Low buildings: small windows on storey rows and bay columns (a column is glazed or not), siding.
float hfy = vPlateauWorldPos.z / 2.85;
float hfx = facadeAxis / (3.3 + buildingRnd2 * 1.3);
float haax = max(fwidth(hfx), 1e-4);
float haay = max(fwidth(hfy), 1e-4);
float hwx = fract(hfx);
float hwy = fract(hfy);
float hcolumn = step(0.35, plateauHash(vec2(floor(hfx), vPlateauFeatureId * 0.731 + 11.0)));
float hx = smoothstep(0.28 - haax, 0.28 + haax, hwx) * (1.0 - smoothstep(0.72 - haax, 0.72 + haax, hwx));
float hy = smoothstep(0.32 - haay, 0.32 + haay, hwy) * (1.0 - smoothstep(0.82 - haay, 0.82 + haay, hwy));
float hdetail = 1.0 - smoothstep(0.18, 0.45, max(haax, haay));
float houseWindow = houseWall * mix(0.65 * 0.44 * 0.5, hcolumn * hx * hy, hdetail);
gl_FragColor.rgb = mix(gl_FragColor.rgb, vec3(0.24, 0.28, 0.33), houseWindow * 0.72);
float hsiding = houseWall * (1.0 - smoothstep(0.0, 0.12, fract(vPlateauWorldPos.z / 0.42))) * hdetail;
gl_FragColor.rgb *= 1.0 - hsiding * 0.10;
gl_FragColor.rgb += vec3(1.0, 0.72, 0.40) * houseWindow * step(1.0 - uCityWindows * 0.6, cpanel) * uCityWindows;
`;

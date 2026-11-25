import * as THREE from "three";
import { cityUniforms, type CityUniforms } from "./city-materials.js";
import { glslFloat, PALETTE_WALL_GAIN, PLATEAU_PHOTO_GAMMA, STUDY_MODEL_WHITE, UNTEXTURED_BASE_MAX } from "./city-tone.js";
import { analyzeTextureTone } from "./plateau-texture-tone.js";

export { analyzeTextureTone, type TextureToneAnalysis } from "./plateau-texture-tone.js";
import {
  applyWetGroundShader,
  COMFY_WINDOW_GLOW,
  comfyFacadeMapGlsl,
  paletteTexture,
  plateauFacadeTextureUniforms,
  type PlateauFacadeTextureUniforms,
  plateauRoofUniforms,
  type PlateauRoofUniforms,
  resolveIdVariants,
  roofPhotoGlsl,
  ROOF_PHOTO_UNIFORMS,
  UNTEXTURED_FACADE,
  variantTexture
} from "./plateau-facade-glsl.js";

export { applyWetGroundShader, plateauRoofUniforms, resolveIdVariants };

export interface PlateauAppearanceOptions {
  palette?: Array<string | null>;
  /** Per-feature atlas cell index (0..5), or null/undefined to use deterministic hash. */
  variants?: Array<number | null>;
  seed?: number;
  /**
   * false keeps the source colors of untextured buildings (no palette, no darkening). The
   * procedural facade pattern is applied either way: no building may be left as a flat,
   * featureless surface. Photo textures are brought to the tone of the aerial photo either way.
   */
  recolor?: boolean;
  /** Uniforms of the scene these buildings belong to (paint wave, windows, roof photo). */
  uniforms?: FacadeUniforms;
  /** Aerial roof photo also on upward faces of photo-textured buildings (pale, coarse PLATEAU roofs). */
  roofPhotoOnTextured?: boolean;
}

export interface FacadeUniforms {
  city: CityUniforms;
  roof: PlateauRoofUniforms;
  facade?: PlateauFacadeTextureUniforms;
}

const defaultUniforms: FacadeUniforms = {
  city: cityUniforms,
  roof: plateauRoofUniforms,
  facade: plateauFacadeTextureUniforms
};

export interface PlateauAppearanceResult {
  preservedTexturedMaterials: number;
  styledUntexturedMaterials: number;
}

/**
 * PLATEAU photo-textured materials ask for metalness 0.5 / roughness 0.3 and untextured ones for
 * roughness 0. Without an environment map a metal reflects nothing, so the photo came out near
 * black; the texture already is the facade's look, so treat every surface as rough non-metal.
 */
export function neutralizePbr(material: THREE.Material): void {
  const standard = material as THREE.MeshStandardMaterial;
  if (!standard.isMeshStandardMaterial) return;
  standard.metalness = 0;
  standard.roughness = Math.max(standard.roughness, 0.85);
}

/**
 * Untextured PLATEAU materials are pure white, which clips on every roof under the neutral light.
 * Dim them to the study model white, once per material (meshes share materials).
 */
export function toStudyModelWhite(material: THREE.Material): void {
  const standard = material as THREE.MeshStandardMaterial;
  if (!standard.isMeshStandardMaterial || standard.map || standard.userData.studyModelWhite) return;
  standard.color.multiplyScalar(STUDY_MODEL_WHITE);
  standard.userData.studyModelWhite = true;
}

function clampUntexturedBase(material: THREE.MeshStandardMaterial): void {
  material.roughness = 1;
  material.metalness = 0;
  const maxChannel = Math.max(material.color.r, material.color.g, material.color.b);
  if (maxChannel > UNTEXTURED_BASE_MAX) {
    material.color.multiplyScalar(UNTEXTURED_BASE_MAX / maxChannel);
  }
}

// Brings a PLATEAU photo texture to the tone of the aerial photo (city-tone.ts). The material
// color stays outside the curve: it only carries the tone-down of washed-out atlases.
const PHOTO_CURVE = `diffuseColor.rgb = diffuse * pow(max(sampledDiffuseColor.rgb, vec3(0.0)), vec3(${glslFloat(PLATEAU_PHOTO_GAMMA)}));`;

function attachFacadeShader(
  material: THREE.MeshStandardMaterial,
  seed: number,
  palette?: THREE.DataTexture | null,
  uniforms: FacadeUniforms = defaultUniforms,
  rawColor?: THREE.Color,
  variants?: THREE.DataTexture | null,
  roofOnPhoto = false
): void {
  const usePalette = !material.map && Boolean(palette);
  const untextured = !material.map;
  const photoRoof = !untextured && roofOnPhoto;
  const paletteSize = palette ? Math.max(1, palette.image.width) : 1;
  const variantSize = variants ? Math.max(1, variants.image.width) : 0;
  material.customProgramCacheKey = () =>
    `plateau-facade-v4-${seed}-${usePalette ? paletteSize : "map"}-${untextured ? "u" : photoRoof ? "tr" : "t"}${variantSize ? `-v${variantSize}` : ""}`;
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uPlateauSeed = { value: seed };
    shader.uniforms.uCityWindows = uniforms.city.uCityWindows;
    Object.assign(shader.uniforms, uniforms.facade ?? plateauFacadeTextureUniforms);
    if (variants) {
      shader.uniforms.uComfyVariantMap = { value: variants };
      shader.uniforms.uComfyVariantSize = { value: variantSize };
    }
    if (untextured || photoRoof) Object.assign(shader.uniforms, uniforms.roof);
    if (untextured) {
      shader.uniforms.uCityGrowOrigin = uniforms.city.uCityGrowOrigin;
      shader.uniforms.uCityGrowWidth = uniforms.city.uCityGrowWidth;
      shader.uniforms.uCityPaintRadius = uniforms.city.uCityPaintRadius;
      shader.uniforms.uPlateauRawColor = { value: rawColor ?? material.color.clone() };
    }
    if (usePalette && palette) {
      shader.uniforms.uPlateauPalette = { value: palette };
      shader.uniforms.uPlateauPaletteSize = { value: paletteSize };
    }
    shader.vertexShader = shader.vertexShader
      .replace(
        "#include <common>",
        `#include <common>
attribute float _batchid;
varying float vPlateauFeatureId;
varying vec3 vPlateauWorldPos;
varying vec3 vPlateauWorldNormal;
${untextured ? "uniform vec2 uCityGrowOrigin;\nuniform float uCityGrowWidth;\nuniform float uCityPaintRadius;\nvarying float vPlateauPaint;" : ""}`
      )
      .replace(
        "#include <begin_vertex>",
        `#include <begin_vertex>
vPlateauFeatureId = _batchid;
vec4 plateauWorld = modelMatrix * vec4(transformed, 1.0);
vPlateauWorldPos = plateauWorld.xyz;
vPlateauWorldNormal = normalize(mat3(modelMatrix) * objectNormal);
${untextured ? "vPlateauPaint = clamp((uCityPaintRadius - distance(plateauWorld.xy, uCityGrowOrigin)) / uCityGrowWidth, 0.0, 1.0);" : ""}`
      );
    // Before the paint wave an untextured building looks as PLATEAU ships it.
    const roofHook = untextured
      ? `${roofPhotoGlsl(false)}\ndiffuseColor.rgb = mix(uPlateauRawColor, diffuseColor.rgb, vPlateauPaint);`
      : photoRoof ? roofPhotoGlsl(true) : "";
    const colorHook = (usePalette
      ? `#include <color_fragment>
float plateauIndex = clamp(floor(vPlateauFeatureId + 0.5), 0.0, uPlateauPaletteSize - 1.0);
vec4 plateauSample = texture2D(uPlateauPalette, vec2((plateauIndex + 0.5) / uPlateauPaletteSize, 0.5));
if (plateauSample.a > 0.5) {
  diffuseColor.rgb = plateauSample.rgb * ${glslFloat(PALETTE_WALL_GAIN)};
}
float plateauTall = plateauSample.a > 0.9 || plateauSample.a < 0.5 ? 1.0 : 0.0;`
      : "#include <color_fragment>\nfloat plateauTall = 1.0;") + roofHook;
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <common>",
        `#include <common>
${usePalette ? "uniform sampler2D uPlateauPalette;\nuniform float uPlateauPaletteSize;" : ""}
${variantSize > 0 ? "uniform sampler2D uComfyVariantMap;\nuniform float uComfyVariantSize;" : ""}
uniform float uPlateauSeed;
uniform float uCityWindows;
uniform sampler2D uComfyGlass;
uniform sampler2D uComfyShutter;
uniform sampler2D uComfyAtlas;
uniform float uComfyAtlasOn;
uniform float uComfyWallMix;
uniform vec2 uComfyTileMeters;
uniform float uComfyGroundZ;
uniform float uComfyShutterHeight;
${untextured ? `${ROOF_PHOTO_UNIFORMS}\nuniform vec3 uPlateauRawColor;\nvarying float vPlateauPaint;` : photoRoof ? `${ROOF_PHOTO_UNIFORMS}\nuniform float uPlateauRoofMaxZ;` : ""}
varying float vPlateauFeatureId;
varying vec3 vPlateauWorldPos;
varying vec3 vPlateauWorldNormal;
float plateauHash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}`
      )
      .replace("#include <color_fragment>", colorHook)
      .replace("#include <map_fragment>", `${untextured ? "#include <map_fragment>" : `#include <map_fragment>\n${PHOTO_CURVE}`}\n${comfyFacadeMapGlsl(variantSize)}`)
      .replace(
        "#include <dithering_fragment>",
        `vec3 facadeN = normalize(vPlateauWorldNormal);
float buildingRnd = plateauHash(vec2(vPlateauFeatureId + 0.37, uPlateauSeed));
float buildingRnd2 = plateauHash(vec2(vPlateauFeatureId * 1.71 + 5.3, uPlateauSeed * 0.61));
float cmax = max(gl_FragColor.r, max(gl_FragColor.g, gl_FragColor.b));
float cmin = min(gl_FragColor.r, min(gl_FragColor.g, gl_FragColor.b));
float graySurface = 0.0;
vec3 warmTint = vec3(1.08, 0.96, 0.86);
vec3 coolTint = vec3(0.86, 0.96, 1.08);
vec3 buildingTint = mix(warmTint, coolTint, buildingRnd);
buildingTint *= 0.84 + buildingRnd2 * 0.30;
gl_FragColor.rgb *= mix(vec3(1.0), buildingTint, graySurface * 0.78);
float facadeWall = smoothstep(0.58, 0.90, 1.0 - abs(facadeN.z));
float facadeAxis = abs(facadeN.x) > abs(facadeN.y) ? vPlateauWorldPos.y : vPlateauWorldPos.x;
float facadeFloor = floor(vPlateauWorldPos.z / (2.9 + buildingRnd * 0.65));
float facadeBay = floor(facadeAxis / (3.5 + buildingRnd2 * 1.8));
vec2 facadeCell = vec2(facadeBay + vPlateauFeatureId * 0.17, facadeFloor);
float facadeRnd = plateauHash(facadeCell);
float facadeX = fract(facadeAxis / (3.4 + buildingRnd2 * 1.7));
float facadeY = fract(vPlateauWorldPos.z / (2.9 + buildingRnd * 0.65));
float facadeWindow = smoothstep(0.12, 0.20, facadeX) * (1.0 - smoothstep(0.72, 0.88, facadeX));
facadeWindow *= smoothstep(0.18, 0.29, facadeY) * (1.0 - smoothstep(0.66, 0.80, facadeY));
float facadeBand = 1.0 - smoothstep(0.06, 0.13, min(facadeY, 1.0 - facadeY));
vec3 facadeGlass = mix(vec3(0.045, 0.065, 0.075), vec3(0.14, 0.17, 0.18), facadeRnd);
gl_FragColor.rgb = mix(gl_FragColor.rgb, facadeGlass, graySurface * facadeWall * facadeWindow * (0.52 + facadeRnd * 0.24));
gl_FragColor.rgb *= 1.0 - graySurface * facadeWall * facadeBand * 0.11;
float facadeRoof = smoothstep(0.72, 0.92, abs(facadeN.z));
vec2 roofCell = floor(vPlateauWorldPos.xy / (6.5 + buildingRnd * 2.5));
vec2 roofUv = fract(vPlateauWorldPos.xy / (6.5 + buildingRnd * 2.5));
float roofRnd = plateauHash(roofCell + vPlateauFeatureId);
float roofEdge = min(min(roofUv.x, 1.0 - roofUv.x), min(roofUv.y, 1.0 - roofUv.y));
float roofSeam = 1.0 - smoothstep(0.025, 0.065, roofEdge);
float roofUnit = step(0.72, roofRnd) * smoothstep(0.18, 0.24, roofUv.x) * (1.0 - smoothstep(0.62, 0.68, roofUv.x));
roofUnit *= smoothstep(0.20, 0.27, roofUv.y) * (1.0 - smoothstep(0.58, 0.65, roofUv.y));
gl_FragColor.rgb *= 1.0 - graySurface * facadeRoof * roofSeam * 0.10;
gl_FragColor.rgb = mix(gl_FragColor.rgb, vec3(0.17, 0.19, 0.20), graySurface * facadeRoof * roofUnit * 0.32);
float facadeLit = step(1.0 - uCityWindows * 0.7, plateauHash(facadeCell + 4.2));
gl_FragColor.rgb += vec3(1.0, 0.72, 0.40) * graySurface * facadeWall * facadeWindow * facadeLit * uCityWindows * 1.1;
${COMFY_WINDOW_GLOW}${untextured ? UNTEXTURED_FACADE : ""}#include <dithering_fragment>`
      );
  };
  material.needsUpdate = true;
}

function hash01(seed: number): number {
  const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453123;
  return x - Math.floor(x);
}

function tintUnbatched(material: THREE.MeshStandardMaterial, seed: number): void {
  clampUntexturedBase(material);
  const r1 = hash01(seed + 0.37);
  const r2 = hash01(seed * 1.71 + 5.3);
  const scale = 0.84 + r2 * 0.3;
  const tintR = (1.08 * (1 - r1) + 0.86 * r1) * scale;
  const tintG = 0.96 * scale;
  const tintB = (0.86 * (1 - r1) + 1.08 * r1) * scale;
  material.color.setRGB(
    Math.min(1, material.color.r * tintR),
    Math.min(1, material.color.g * tintG),
    Math.min(1, material.color.b * tintB)
  );
}

export function applyPlateauBuildingAppearance(
  root: THREE.Object3D,
  options: PlateauAppearanceOptions = {}
): PlateauAppearanceResult {
  const seed = options.seed ?? 1;
  const recolor = options.recolor ?? true;
  const uniforms = options.uniforms ?? defaultUniforms;
  const palette = recolor ? options.palette ?? [] : [];
  const texture = palette.length > 0 ? paletteTexture(palette) : null;
  const varTex = options.variants && options.variants.length > 0 ? variantTexture(options.variants) : null;
  const result: PlateauAppearanceResult = {
    preservedTexturedMaterials: 0,
    styledUntexturedMaterials: 0
  };
  let meshIndex = 0;

  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (!mesh.isMesh || !mesh.geometry) {
      return;
    }
    const batchAttr =
      mesh.geometry.getAttribute("_batchid") ??
      mesh.geometry.getAttribute("_BATCHID") ??
      mesh.geometry.getAttribute("_FEATURE_ID_0") ??
      mesh.geometry.getAttribute("_feature_id_0");
    if (!mesh.geometry.getAttribute("_batchid") && batchAttr) {
      mesh.geometry.setAttribute("_batchid", batchAttr);
    }
    const transformMaterial = (mat: THREE.Material): THREE.Material => {
      const std = mat as THREE.MeshStandardMaterial;
      if (std.map) {
        result.preservedTexturedMaterials++;
        const clone = std.clone();
        // Some PLATEAU materials carry a base color factor (0.7 on half of the 2025 Tokyo LOD2
        // textures) that multiplies the photo once more; the photo is the color.
        clone.color.setRGB(1, 1, 1);
        const analysis = analyzeTextureTone(clone.map);
        if (recolor && analysis.tone < 1) {
          clone.color.multiplyScalar(analysis.tone);
        }
        attachFacadeShader(clone, seed + meshIndex * 0.13, null, uniforms, undefined, varTex, options.roofPhotoOnTextured ?? false);
        return clone;
      }
      result.styledUntexturedMaterials++;
      const clone = std.clone();
      const raw = std.color.clone();
      if (!recolor) {
        attachFacadeShader(clone, seed + meshIndex * 0.13, null, uniforms, raw, varTex);
      } else if (batchAttr) {
        clampUntexturedBase(clone);
        attachFacadeShader(clone, seed + meshIndex * 0.13, texture, uniforms, raw, varTex);
      } else {
        tintUnbatched(clone, seed + meshIndex * 0.13);
        attachFacadeShader(clone, seed + meshIndex * 0.13, null, uniforms, raw, varTex);
      }
      return clone;
    };
    mesh.material = Array.isArray(mesh.material)
      ? mesh.material.map(transformMaterial)
      : transformMaterial(mesh.material);
    meshIndex++;
  });

  return result;
}

function seedFromString(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) / 4294967295) * 100;
}

export function applyBuildingAppearance(
  root: THREE.Object3D,
  paletteOrOptions?: Array<string | null> | PlateauAppearanceOptions,
  seedKey?: string | number,
  recolor = true,
  uniforms?: FacadeUniforms,
  variants?: Array<number | null>,
  roofPhotoOnTextured = false
): PlateauAppearanceResult {
  if (Array.isArray(paletteOrOptions)) {
    const seed =
      typeof seedKey === "number"
        ? seedKey
        : typeof seedKey === "string"
          ? seedFromString(seedKey)
          : 1;
    return applyPlateauBuildingAppearance(root, { palette: paletteOrOptions, variants, seed, recolor, roofPhotoOnTextured, ...(uniforms ? { uniforms } : {}) });
  }
  return applyPlateauBuildingAppearance(root, paletteOrOptions);
}

/** Set opacity on building meshes (skipping ground shadow materials). */
export function applyBuildingOpacity(root: THREE.Object3D, opacity: number): void {
  const clamped = Math.min(1, Math.max(0, opacity));
  const isTransparent = clamped < 0.999;
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (!mesh.isMesh || !mesh.material) return;
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const mat of mats) {
      if (!mat || mat.name === "city-shadow") continue;
      mat.transparent = isTransparent;
      mat.opacity = clamped;
      mat.depthWrite = !isTransparent;
      mat.colorWrite = true;
    }
  });
}

/** Toggle depth-only pre-pass mode on building meshes so transparent buildings render front-surface only without overdraw. */
export function setBuildingDepthPass(root: THREE.Object3D, enabled: boolean): void {
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (!mesh.isMesh || !mesh.material) return;
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    const isShadow = mats.some((mat) => mat && mat.name === "city-shadow");
    if (isShadow) {
      if (enabled) {
        mesh.userData._prepassVisible = mesh.visible;
        mesh.visible = false;
      } else if (mesh.userData._prepassVisible !== undefined) {
        mesh.visible = Boolean(mesh.userData._prepassVisible);
        delete mesh.userData._prepassVisible;
      }
      return;
    }
    for (const mat of mats) {
      if (!mat) continue;
      if (enabled) {
        mat.colorWrite = false;
        mat.depthWrite = true;
        mat.transparent = false;
      } else {
        mat.colorWrite = true;
      }
    }
  });
}



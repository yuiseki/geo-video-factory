import * as THREE from "three";
import { cityUniforms } from "./city-materials.js";
import { plateauRoofUniforms, UNTEXTURED_FACADE } from "./plateau-facade-glsl.js";

export { plateauRoofUniforms };

export interface PlateauAppearanceOptions {
  palette?: Array<string | null>;
  seed?: number;
  /**
   * false keeps the source colors (no palette, no darkening). The procedural facade pattern is
   * applied either way: no building may be left as a flat, featureless surface.
   */
  recolor?: boolean;
}

export interface PlateauAppearanceResult {
  preservedTexturedMaterials: number;
  styledUntexturedMaterials: number;
}

export interface TextureToneAnalysis {
  tone: number;
  bland: boolean;
}

const toneCache = new WeakMap<THREE.Texture, TextureToneAnalysis>();

function extractTexturePixels(image: unknown): Uint8Array | Uint8ClampedArray | null {
  if (!image || typeof image !== "object") {
    return null;
  }
  const dataImage = image as { data?: unknown; width?: number; height?: number };
  if (
    (dataImage.data instanceof Uint8Array || dataImage.data instanceof Uint8ClampedArray) &&
    dataImage.data.length >= 4
  ) {
    return dataImage.data;
  }
  if (typeof document === "undefined") {
    return null;
  }
  const width = Number(dataImage.width) || 0;
  const height = Number(dataImage.height) || 0;
  if (width <= 0 || height <= 0) {
    return null;
  }
  try {
    const size = 32;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) {
      return null;
    }
    ctx.drawImage(image as CanvasImageSource, 0, 0, size, size);
    return ctx.getImageData(0, 0, size, size).data;
  } catch {
    return null;
  }
}

export function analyzeTextureTone(texture?: THREE.Texture | null): TextureToneAnalysis {
  if (!texture) {
    return { tone: 1, bland: false };
  }
  const cached = toneCache.get(texture);
  if (cached) {
    return cached;
  }
  const pixels = extractTexturePixels(texture.image);
  if (!pixels) {
    return { tone: 1, bland: false };
  }
  let count = 0;
  let sum = 0;
  let sumSq = 0;
  let bright = 0;
  for (let i = 0; i + 3 < pixels.length; i += 4) {
    const a = pixels[i + 3] ?? 0;
    if (a < 16) {
      continue;
    }
    const r = pixels[i] ?? 0;
    const g = pixels[i + 1] ?? 0;
    const b = pixels[i + 2] ?? 0;
    const y = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
    count++;
    sum += y;
    sumSq += y * y;
    if (y > 0.78) {
      bright++;
    }
  }
  if (!count) {
    return { tone: 1, bland: false };
  }
  const mean = sum / count;
  const variance = Math.max(0, sumSq / count - mean * mean);
  const spread = Math.sqrt(variance);
  const share = bright / count;
  let tone = 1;
  if (share > 0.42 || mean > 0.74) {
    tone = 0.64;
  } else if (share > 0.24 || mean > 0.64) {
    tone = 0.78;
  }
  const result = {
    tone,
    bland: spread < 0.105 && mean > 0.28
  };
  toneCache.set(texture, result);
  return result;
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

function parseHexBytes(hex: string | null | undefined): [number, number, number, number] | null {
  if (!hex || !/^#[0-9a-f]{6}([0-9a-f]{2})?$/i.test(hex)) {
    return null;
  }
  return [
    Number.parseInt(hex.slice(1, 3), 16),
    Number.parseInt(hex.slice(3, 5), 16),
    Number.parseInt(hex.slice(5, 7), 16),
    hex.length === 9 ? Number.parseInt(hex.slice(7, 9), 16) : 255
  ];
}

function paletteTexture(palette: Array<string | null>): THREE.DataTexture {
  const count = Math.max(1, palette.length);
  const data = new Uint8Array(count * 4);
  for (let i = 0; i < count; i++) {
    const rgb = parseHexBytes(palette[i]);
    if (rgb) {
      data[i * 4] = rgb[0];
      data[i * 4 + 1] = rgb[1];
      data[i * 4 + 2] = rgb[2];
      // alpha: 255 tall building (curtain wall), 200 low building (house facade)
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



function clampUntexturedBase(material: THREE.MeshStandardMaterial): void {
  material.roughness = 1;
  material.metalness = 0;
  const maxChannel = Math.max(material.color.r, material.color.g, material.color.b);
  if (maxChannel > 0.45) {
    material.color.multiplyScalar(0.45 / maxChannel);
  }
}

function attachFacadeShader(
  material: THREE.MeshStandardMaterial,
  seed: number,
  palette?: THREE.DataTexture | null
): void {
  const usePalette = !material.map && Boolean(palette);
  const untextured = !material.map;
  const paletteSize = palette ? Math.max(1, palette.image.width) : 1;
  material.customProgramCacheKey = () =>
    `plateau-facade-v3-${seed}-${usePalette ? paletteSize : "map"}-${untextured ? "u" : "t"}`;
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uPlateauSeed = { value: seed };
    shader.uniforms.uCityWindows = cityUniforms.uCityWindows;
    if (untextured) Object.assign(shader.uniforms, plateauRoofUniforms);
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
varying vec3 vPlateauWorldNormal;`
      )
      .replace(
        "#include <begin_vertex>",
        `#include <begin_vertex>
vPlateauFeatureId = _batchid;
vec4 plateauWorld = modelMatrix * vec4(transformed, 1.0);
vPlateauWorldPos = plateauWorld.xyz;
vPlateauWorldNormal = normalize(mat3(modelMatrix) * objectNormal);`
      );
    const roofHook = untextured
      ? `
float plateauRoofUp = smoothstep(0.72, 0.92, abs(normalize(vPlateauWorldNormal).z));
vec3 plateauRoofColor = texture2D(uPlateauRoofPhoto, (vPlateauWorldPos.xy - uPlateauRoofMin) / uPlateauRoofSize).rgb;
diffuseColor.rgb = mix(diffuseColor.rgb, plateauRoofColor, plateauRoofUp * uPlateauRoofOn);`
      : "";
    const colorHook = (usePalette
      ? `#include <color_fragment>
float plateauIndex = clamp(floor(vPlateauFeatureId + 0.5), 0.0, uPlateauPaletteSize - 1.0);
vec4 plateauSample = texture2D(uPlateauPalette, vec2((plateauIndex + 0.5) / uPlateauPaletteSize, 0.5));
if (plateauSample.a > 0.5) {
  diffuseColor.rgb = plateauSample.rgb;
}
float plateauTall = plateauSample.a > 0.9 || plateauSample.a < 0.5 ? 1.0 : 0.0;`
      : "#include <color_fragment>\nfloat plateauTall = 1.0;") + roofHook;
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <common>",
        `#include <common>
${usePalette ? "uniform sampler2D uPlateauPalette;\nuniform float uPlateauPaletteSize;" : ""}
uniform float uPlateauSeed;
uniform float uCityWindows;
${untextured ? "uniform sampler2D uPlateauRoofPhoto;\nuniform vec2 uPlateauRoofMin;\nuniform vec2 uPlateauRoofSize;\nuniform float uPlateauRoofOn;" : ""}
varying float vPlateauFeatureId;
varying vec3 vPlateauWorldPos;
varying vec3 vPlateauWorldNormal;
float plateauHash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}`
      )
      .replace("#include <color_fragment>", colorHook)
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
${untextured ? UNTEXTURED_FACADE : ""}#include <dithering_fragment>`
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
  const palette = recolor ? options.palette ?? [] : [];
  const texture = palette.length > 0 ? paletteTexture(palette) : null;
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
      mesh.geometry.getAttribute("_batchid") ?? mesh.geometry.getAttribute("_FEATURE_ID_0");
    if (!mesh.geometry.getAttribute("_batchid") && batchAttr) {
      mesh.geometry.setAttribute("_batchid", batchAttr);
    }
    const transformMaterial = (mat: THREE.Material): THREE.Material => {
      const std = mat as THREE.MeshStandardMaterial;
      if (std.map) {
        result.preservedTexturedMaterials++;
        const clone = std.clone();
        const analysis = analyzeTextureTone(clone.map);
        if (recolor && analysis.tone < 1) {
          clone.color.multiplyScalar(analysis.tone);
        }
        attachFacadeShader(clone, seed + meshIndex * 0.13, null);
        return clone;
      }
      result.styledUntexturedMaterials++;
      const clone = std.clone();
      if (!recolor) {
        attachFacadeShader(clone, seed + meshIndex * 0.13, null);
      } else if (batchAttr) {
        clampUntexturedBase(clone);
        attachFacadeShader(clone, seed + meshIndex * 0.13, texture);
      } else {
        tintUnbatched(clone, seed + meshIndex * 0.13);
        attachFacadeShader(clone, seed + meshIndex * 0.13, null);
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
  recolor = true
): PlateauAppearanceResult {
  if (Array.isArray(paletteOrOptions)) {
    const seed =
      typeof seedKey === "number"
        ? seedKey
        : typeof seedKey === "string"
          ? seedFromString(seedKey)
          : 1;
    return applyPlateauBuildingAppearance(root, { palette: paletteOrOptions, seed, recolor });
  }
  return applyPlateauBuildingAppearance(root, paletteOrOptions);
}



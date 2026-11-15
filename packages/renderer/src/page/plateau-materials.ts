import * as THREE from 'three';

export interface AppearanceResult {
  patchedMaterials: number;
  preservedTexturedMaterials: number;
  fallbackMaterials: number;
}

function hash(value: string): number {
  let result = 2166136261;
  for (const character of value) result = Math.imul(result ^ character.charCodeAt(0), 16777619);
  return result >>> 0;
}

function paletteColor(value: string | null | undefined, index: number, seed: string): [number, number, number] {
  if (value && /^#[0-9a-f]{6}$/i.test(value)) {
    return [1, 3, 5].map((offset) => parseInt(value.slice(offset, offset + 2), 16) / 255) as [number, number, number];
  }
  const noise = hash(`${seed}:${index}`);
  const hue = (noise % 360) / 360;
  const saturation = 0.07 + ((noise >>> 9) % 13) / 100;
  const lightness = 0.48 + ((noise >>> 17) % 17) / 100;
  const color = new THREE.Color().setHSL(hue, saturation, lightness);
  return [color.r, color.g, color.b];
}

function paletteTexture(palette: (string | null)[], seed: string): THREE.DataTexture {
  const colors = palette.length ? palette : [null];
  const data = new Uint8Array(colors.length * 4);
  colors.forEach((color, index) => {
    const rgb = paletteColor(color, index, seed);
    data[index * 4] = Math.round(rgb[0] * 255);
    data[index * 4 + 1] = Math.round(rgb[1] * 255);
    data[index * 4 + 2] = Math.round(rgb[2] * 255);
    data[index * 4 + 3] = 255;
  });
  const texture = new THREE.DataTexture(data, colors.length, 1, THREE.RGBAFormat, THREE.UnsignedByteType);
  texture.magFilter = THREE.NearestFilter;
  texture.minFilter = THREE.NearestFilter;
  texture.generateMipmaps = false;
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

function batchAttribute(geometry: THREE.BufferGeometry): string | undefined {
  return Object.keys(geometry.attributes).find((name) => /batch.?id|feature.?id/i.test(name));
}

function patchPaletteShader(material: THREE.Material, attribute: string, texture: THREE.DataTexture, size: number): void {
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uPlateauPalette = { value: texture };
    shader.uniforms.uPlateauPaletteSize = { value: size };
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', `#include <common>\nattribute float ${attribute};\nvarying float vPlateauFeatureId;`)
      .replace('#include <begin_vertex>', `#include <begin_vertex>\nvPlateauFeatureId = ${attribute};`);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform sampler2D uPlateauPalette;\nuniform float uPlateauPaletteSize;\nvarying float vPlateauFeatureId;')
      .replace('#include <color_fragment>', `#include <color_fragment>\nfloat plateauIndex = clamp(floor(vPlateauFeatureId + 0.5), 0.0, uPlateauPaletteSize - 1.0);\nvec3 plateauColor = texture2D(uPlateauPalette, vec2((plateauIndex + 0.5) / uPlateauPaletteSize, 0.5)).rgb;\ndiffuseColor.rgb = plateauColor;`);
  };
  material.customProgramCacheKey = () => `plateau-palette-v1:${attribute}:${size}`;
  material.needsUpdate = true;
}

function tintUnbatched(material: THREE.Material, seed: string): void {
  const colored = material as THREE.Material & { color?: THREE.Color };
  if (!colored.color) return;
  const variation = hash(seed);
  const tint = [
    0.82 + (variation & 255) / 255 * 0.34,
    0.82 + ((variation >>> 8) & 255) / 255 * 0.34,
    0.82 + ((variation >>> 16) & 255) / 255 * 0.34,
  ];
  colored.color.multiply(new THREE.Color(...tint));
  if (colored instanceof THREE.MeshStandardMaterial) {
    colored.roughness = Math.max(0.72, colored.roughness);
    colored.metalness = Math.min(0.08, colored.metalness);
  }
}

export function applyBuildingAppearance(
  root: THREE.Object3D,
  palette: (string | null)[],
  seed: string,
): AppearanceResult {
  const result: AppearanceResult = { patchedMaterials: 0, preservedTexturedMaterials: 0, fallbackMaterials: 0 };
  const paletteMap = paletteTexture(palette, seed);
  const paletteSize = Math.max(1, palette.length);
  root.traverse((object) => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh) return;
    const attribute = batchAttribute(mesh.geometry);
    const original = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    const next = original.map((source, index) => {
      const hasFacadeTexture = Boolean((source as THREE.Material & { map?: THREE.Texture | null }).map);
      if (hasFacadeTexture) {
        result.preservedTexturedMaterials++;
        return source;
      }
      const material = source.clone();
      if (attribute) {
        patchPaletteShader(material, attribute, paletteMap, paletteSize);
        result.patchedMaterials++;
      } else {
        tintUnbatched(material, `${seed}:${mesh.name || mesh.uuid}:${index}`);
        result.fallbackMaterials++;
      }
      return material;
    });
    mesh.material = Array.isArray(mesh.material) ? next : next[0]!;
  });
  return result;
}

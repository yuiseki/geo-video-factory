import * as THREE from 'three';
import type { createCityUniforms } from './city-materials.js';

/**
 * PLATEAU++ GLBs from packages/pipeline (buildings/pp_bake.py) carry their look: roof photos, wall colours,
 * window patterns and the tone this renderer used to set at draw time (city-tone.ts). Such a tile is drawn as
 * it is; the only thing left to the renderer is lighting the windows at night, through the emissive factor of
 * the pp-wall-* materials (the GLB stores it at 0).
 */
export function isBakedGltf(gltf: { asset?: { version?: string; extras?: Record<string, unknown> } }): boolean {
  return typeof gltf.asset?.extras?.['plateau_pp_bake'] === 'string';
}

export function prepareBakedScene(root: THREE.Object3D, city: ReturnType<typeof createCityUniforms>): void {
  root.traverse((object) => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh) return;
    mesh.frustumCulled = false;
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    const walls = materials.filter((m): m is THREE.MeshStandardMaterial =>
      (m as THREE.MeshStandardMaterial).isMeshStandardMaterial && m.name.startsWith('pp-wall-'));
    if (!walls.length) return;
    mesh.onBeforeRender = () => {
      const lit = city.uCityWindows.value;
      for (const wall of walls) wall.emissive.setScalar(lit);
    };
  });
}

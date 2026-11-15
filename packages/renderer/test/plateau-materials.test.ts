import assert from "node:assert/strict";
import { describe, it } from "node:test";
import * as THREE from "three";
import {
  analyzeTextureTone,
  applyPlateauBuildingAppearance
} from "../src/page/plateau-materials.js";

function makeSolidTexture(r: number, g: number, b: number, a = 255): THREE.DataTexture {
  const data = new Uint8Array(4 * 4 * 4);
  for (let i = 0; i < data.length; i += 4) {
    data[i] = r;
    data[i + 1] = g;
    data[i + 2] = b;
    data[i + 3] = a;
  }
  const texture = new THREE.DataTexture(data, 4, 4);
  texture.needsUpdate = true;
  return texture;
}

describe("plateau-materials", () => {
  it("analyzes texture atlas luma to darken washed-out white atlases", () => {
    const brightWhite = makeSolidTexture(240, 240, 240);
    const brightResult = analyzeTextureTone(brightWhite);
    assert.equal(brightResult.tone, 0.64);
    assert.equal(brightResult.bland, true);

    const mediumBright = makeSolidTexture(175, 175, 175);
    const mediumResult = analyzeTextureTone(mediumBright);
    assert.equal(mediumResult.tone, 0.78);
    assert.equal(mediumResult.bland, true);

    const balancedDark = makeSolidTexture(95, 102, 110);
    const balancedResult = analyzeTextureTone(balancedDark);
    assert.equal(balancedResult.tone, 1);
  });

  it("preserves textured materials while adding chroma-gated procedural facade shader and tone", () => {
    const geometry = new THREE.BoxGeometry(10, 10, 20);
    const count = geometry.attributes.position!.count;
    geometry.setAttribute("_batchid", new THREE.BufferAttribute(new Float32Array(count), 1));
    const map = makeSolidTexture(235, 235, 235);
    const material = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      map,
      roughness: 0.3,
      metalness: 0.5
    });
    const mesh = new THREE.Mesh(geometry, material);
    const root = new THREE.Group();
    root.add(mesh);

    const result = applyPlateauBuildingAppearance(root, {
      palette: ["#aa5533"],
      seed: 1
    });

    const updated = mesh.material as THREE.MeshStandardMaterial;
    assert.equal(result.preservedTexturedMaterials, 1);
    assert.equal(result.styledUntexturedMaterials, 0);
    assert.equal(updated.map, map);
    assert.equal(updated.metalness, 0.5);
    assert.equal(updated.roughness, 0.3);
    assert.ok(updated.color.r < 0.7 && updated.color.r > 0.6);

    const shader = {
      uniforms: {} as Record<string, THREE.IUniform>,
      vertexShader: "#include <common>\n#include <begin_vertex>",
      fragmentShader: "#include <common>\n#include <color_fragment>\n#include <dithering_fragment>"
    };
    updated.onBeforeCompile(shader as THREE.WebGLProgramParametersWithUniforms, {} as THREE.WebGLRenderer);
    assert.equal("uPlateauPalette" in shader.uniforms, false);
    assert.match(shader.fragmentShader, /graySurface = 1\.0 - smoothstep\(0\.07, 0\.19, cmax - cmin\)/);
    assert.match(shader.fragmentShader, /facadeGlass/);
  });

  it("applies feature palette and procedural facade shader to untextured materials without rainbow hues", () => {
    const geometry = new THREE.BoxGeometry(10, 10, 20);
    const count = geometry.attributes.position!.count;
    const batchIds = new Float32Array(count);
    batchIds.fill(1, Math.floor(count / 2));
    geometry.setAttribute("_batchid", new THREE.BufferAttribute(batchIds, 1));
    const material = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.4, metalness: 0.6 });
    const mesh = new THREE.Mesh(geometry, material);
    const root = new THREE.Group();
    root.add(mesh);

    const result = applyPlateauBuildingAppearance(root, {
      palette: ["#c2a878", null],
      seed: 7
    });

    const updated = mesh.material as THREE.MeshStandardMaterial;
    assert.equal(result.preservedTexturedMaterials, 0);
    assert.equal(result.styledUntexturedMaterials, 1);
    assert.notEqual(updated, material);
    assert.equal(updated.roughness, 1);
    assert.equal(updated.metalness, 0);
    assert.ok(Math.max(updated.color.r, updated.color.g, updated.color.b) <= 0.4501);

    const shader = {
      uniforms: {} as Record<string, THREE.IUniform>,
      vertexShader: "#include <common>\n#include <begin_vertex>",
      fragmentShader: "#include <common>\n#include <color_fragment>\n#include <dithering_fragment>"
    };
    updated.onBeforeCompile(shader as THREE.WebGLProgramParametersWithUniforms, {} as THREE.WebGLRenderer);
    assert.ok("uPlateauPalette" in shader.uniforms);
    const paletteTex = shader.uniforms.uPlateauPalette.value as THREE.DataTexture;
    const texData = paletteTex.image.data as Uint8Array;
    // Feature 0 ("#c2a878") has alpha 255 and exact sRGB bytes (not double-gamma-encoded)
    assert.deepEqual(Array.from(texData.slice(0, 4)), [0xc2, 0xa8, 0x78, 255]);
    // Feature 1 (null) has alpha 0 so shader uses neutral base + warm/cool architectural tint
    assert.equal(texData[7], 0);
    assert.match(shader.vertexShader, /attribute float _batchid/);
    assert.match(shader.fragmentShader, /facadeWindow/);
    assert.match(shader.fragmentShader, /roofUnit/);
  });

  it("tints unbatched untextured meshes with warm/cool architectural balance instead of independent RGB channels", () => {
    const geometry = new THREE.BoxGeometry(8, 8, 12);
    const material = new THREE.MeshStandardMaterial({ color: 0xffffff });
    const mesh = new THREE.Mesh(geometry, material);
    const root = new THREE.Group();
    root.add(mesh);

    const result = applyPlateauBuildingAppearance(root, { palette: [], seed: 11 });
    const updated = mesh.material as THREE.MeshStandardMaterial;
    assert.equal(result.styledUntexturedMaterials, 1);
    assert.equal(updated.roughness, 1);
    assert.equal(updated.metalness, 0);
    assert.ok(Math.max(updated.color.r, updated.color.g, updated.color.b) <= 0.60);
    // Green channel sits cleanly between red and blue (warm/cool architectural interpolation, never purple/green spike)
    const minRB = Math.min(updated.color.r, updated.color.b);
    const maxRB = Math.max(updated.color.r, updated.color.b);
    assert.ok(updated.color.g >= minRB - 0.02 && updated.color.g <= maxRB + 0.02);
  });
});

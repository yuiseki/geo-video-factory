import assert from "node:assert/strict";
import { describe, it } from "node:test";
import * as THREE from "three";
import {
  analyzeTextureTone,
  applyBuildingAppearance,
  applyPlateauBuildingAppearance,
  applyWetGroundShader,
  neutralizePbr,
  plateauRoofUniforms,
  resolveIdVariants
} from "../src/page/plateau-materials.js";
import { createCityUniforms } from "../src/page/city-materials.js";
import { createPlateauFacadeTextureUniforms, createPlateauRoofUniforms } from "../src/page/plateau-facade-glsl.js";

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
    // the photo already is the facade: no procedural pattern on top of it
    assert.match(shader.fragmentShader, /float graySurface = 0\.0;/);
    assert.doesNotMatch(shader.fragmentShader, /curtainGlass/);
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

describe("photo-textured PLATEAU materials without an environment map", () => {
  it("render as rough non-metal surfaces, so the photo is not darkened to black", () => {
    const material = new THREE.MeshStandardMaterial({ metalness: 0.5, roughness: 0.3 });
    neutralizePbr(material);
    assert.equal(material.metalness, 0);
    assert.ok(material.roughness >= 0.8);
    const mirror = new THREE.MeshStandardMaterial({ metalness: 0, roughness: 0 });
    neutralizePbr(mirror);
    assert.ok(mirror.roughness >= 0.8, "mirror-smooth untextured walls do not flash highlights");
  });
});

describe("no building is left as a flat, featureless surface", () => {
  it("gives untextured PLATEAU buildings the facade pattern even without a palette", () => {
    const geometry = new THREE.BoxGeometry(10, 10, 20);
    geometry.setAttribute("_batchid", new THREE.BufferAttribute(new Float32Array(geometry.attributes.position!.count), 1));
    const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0xffffff }));
    const root = new THREE.Group();
    root.add(mesh);
    applyPlateauBuildingAppearance(root, { palette: [], recolor: false });
    const updated = mesh.material as THREE.MeshStandardMaterial;
    assert.equal(updated.color.getHex(), 0xffffff, "without recolor the source color is kept");
    const shader = {
      uniforms: {} as Record<string, THREE.IUniform>,
      vertexShader: "#include <common>\n#include <begin_vertex>",
      fragmentShader: "#include <common>\n#include <color_fragment>\n#include <dithering_fragment>"
    };
    updated.onBeforeCompile(shader as THREE.WebGLProgramParametersWithUniforms, {} as THREE.WebGLRenderer);
    assert.match(shader.fragmentShader, /facadeWindow/);
  });
});

describe("untextured PLATEAU buildings in the enhanced render", () => {
  it("get a curtain-wall facade and the aerial photo on their roofs; photo-textured ones keep their photo", () => {
    const geometry = new THREE.BoxGeometry(10, 10, 20);
    geometry.setAttribute("_batchid", new THREE.BufferAttribute(new Float32Array(geometry.attributes.position!.count), 1));
    const plain = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0xffffff }));
    const photo = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ map: makeSolidTexture(120, 110, 100) }));
    const root = new THREE.Group();
    root.add(plain, photo);
    applyPlateauBuildingAppearance(root, { palette: ["#c8c2b6"], seed: 3 });
    const compile = (mesh: THREE.Mesh) => {
      const shader = {
        uniforms: {} as Record<string, THREE.IUniform>,
        vertexShader: "#include <common>\n#include <begin_vertex>",
        fragmentShader: "#include <common>\n#include <color_fragment>\n#include <dithering_fragment>"
      };
      (mesh.material as THREE.MeshStandardMaterial).onBeforeCompile(shader as THREE.WebGLProgramParametersWithUniforms, {} as THREE.WebGLRenderer);
      return shader;
    };
    const a = compile(plain);
    assert.match(a.fragmentShader, /curtainGlass/);
    assert.match(a.fragmentShader, /houseWindow/, "low buildings get a house facade, not a glass tower");
    assert.match(a.fragmentShader, /uPlateauRoofPhoto/);
    assert.equal(a.uniforms.uPlateauRoofPhoto, plateauRoofUniforms.uPlateauRoofPhoto, "roof photo uniforms are shared");
    const b = compile(photo);
    assert.doesNotMatch(b.fragmentShader, /curtainGlass/);
  });
});

describe("untextured PLATEAU buildings change in place as the paint wave passes", () => {
  it("start as PLATEAU shows them and follow the wave of their own scene", () => {
    const geometry = new THREE.BoxGeometry(10, 10, 20);
    geometry.setAttribute("_batchid", new THREE.BufferAttribute(new Float32Array(geometry.attributes.position!.count), 1));
    const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0xffffff }));
    const root = new THREE.Group();
    root.add(mesh);
    const city = createCityUniforms();
    const roof = createPlateauRoofUniforms();
    applyPlateauBuildingAppearance(root, { palette: ["#c8c2b6ff"], seed: 2, uniforms: { city, roof } });
    const shader = {
      uniforms: {} as Record<string, THREE.IUniform>,
      vertexShader: "#include <common>\n#include <begin_vertex>",
      fragmentShader: "#include <common>\n#include <color_fragment>\n#include <dithering_fragment>"
    };
    (mesh.material as THREE.MeshStandardMaterial).onBeforeCompile(shader as THREE.WebGLProgramParametersWithUniforms, {} as THREE.WebGLRenderer);
    assert.match(shader.vertexShader, /vPlateauPaint/);
    assert.match(shader.fragmentShader, /uPlateauRawColor/);
    assert.equal(shader.uniforms.uCityPaintRadius, city.uCityPaintRadius, "the wave of this scene, not a global one");
    assert.equal(shader.uniforms.uPlateauRoofPhoto, roof.uPlateauRoofPhoto);
    assert.deepEqual((shader.uniforms.uPlateauRawColor!.value as THREE.Color).toArray(), [1, 1, 1], "before the wave: PLATEAU's own white");
  });
});

describe("applyBuildingAppearance", () => {
  const scene = () => {
    const geometry = new THREE.BoxGeometry(1, 1, 1);
    geometry.setAttribute("_batchid", new THREE.BufferAttribute(new Float32Array(geometry.attributes.position!.count), 1));
    const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0xffffff }));
    const root = new THREE.Group();
    root.add(mesh);
    return { root, key: () => (mesh.material as THREE.MeshStandardMaterial).customProgramCacheKey() };
  };

  it("derives a stable seed from the tile URL, so a tile looks the same on every render", () => {
    const a = scene();
    const b = scene();
    const c = scene();
    applyBuildingAppearance(a.root, ["#c8c2b6"], "tiles/a.glb");
    applyBuildingAppearance(b.root, ["#c8c2b6"], "tiles/a.glb");
    applyBuildingAppearance(c.root, ["#c8c2b6"], "tiles/b.glb");
    assert.equal(a.key(), b.key());
    assert.notEqual(a.key(), c.key(), "neighbouring tiles do not repeat the same pattern");
  });

  it("accepts a numeric seed, no seed, or a full options object", () => {
    const numeric = scene();
    const result = applyBuildingAppearance(numeric.root, ["#c8c2b6"], 7);
    assert.equal(result.styledUntexturedMaterials, 1);
    assert.match(numeric.key(), /-7-/);
    const fallback = scene();
    applyBuildingAppearance(fallback.root, [null]);
    assert.match(fallback.key(), /-1-/);
    const options = scene();
    applyBuildingAppearance(options.root, { palette: [], seed: 5 });
    assert.match(options.key(), /-5-/);
  });

  it("injects ComfyUI facade texture uniforms when facade uniforms are provided", () => {
    const geometry = new THREE.BoxGeometry(1, 1, 1);
    geometry.setAttribute("_batchid", new THREE.BufferAttribute(new Float32Array(geometry.attributes.position!.count), 1));
    const tex = new THREE.DataTexture(new Uint8Array([255, 255, 255, 255]), 1, 1, THREE.RGBAFormat);
    const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ map: tex }));
    const root = new THREE.Group();
    root.add(mesh);
    const city = createCityUniforms();
    const roof = createPlateauRoofUniforms();
    const facade = createPlateauFacadeTextureUniforms();
    facade.uComfyWallMix.value = 0.85;
    applyPlateauBuildingAppearance(root, { seed: 3, uniforms: { city, roof, facade } });
    const shader = {
      uniforms: {} as Record<string, THREE.IUniform>,
      vertexShader: "#include <common>\n#include <begin_vertex>",
      fragmentShader: "#include <common>\n#include <color_fragment>\n#include <map_fragment>\n#include <dithering_fragment>"
    };
    (mesh.material as THREE.MeshStandardMaterial).onBeforeCompile(shader as THREE.WebGLProgramParametersWithUniforms, {} as THREE.WebGLRenderer);
    assert.match(shader.fragmentShader, /uComfyGlass/);
    assert.match(shader.fragmentShader, /uComfyShutter/);
    assert.match(shader.fragmentShader, /uComfyAtlas/);
    assert.equal(shader.uniforms.uComfyWallMix!.value, 0.85);
  });

  it("aliases uppercase _BATCHID attribute to _batchid for PLATEAU GLB compatibility", () => {
    const geometry = new THREE.BoxGeometry(1, 1, 1);
    geometry.setAttribute("_BATCHID", new THREE.BufferAttribute(new Float32Array(geometry.attributes.position!.count), 1));
    const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0xffffff }));
    const root = new THREE.Group();
    root.add(mesh);
    applyPlateauBuildingAppearance(root, { variants: [2, 4], seed: 1 });
    assert.ok(geometry.getAttribute("_batchid"), "_BATCHID should be aliased to _batchid");
  });

  it("maps tile building IDs to atlas variant indices via resolveIdVariants and flips WebGL atlas row", () => {
    const ids = ["bldg_qfront", "bldg_unknown", "bldg_seibu"];
    const variants = resolveIdVariants(ids, { bldg_qfront: 0, bldg_seibu: 3 });
    assert.deepEqual(variants, [0, null, 3]);

    const geometry = new THREE.BoxGeometry(1, 1, 1);
    geometry.setAttribute("_BATCHID", new THREE.BufferAttribute(new Float32Array(geometry.attributes.position!.count), 1));
    const tex = new THREE.DataTexture(new Uint8Array([255, 255, 255, 255]), 1, 1, THREE.RGBAFormat);
    const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ map: tex }));
    const root = new THREE.Group();
    root.add(mesh);
    applyPlateauBuildingAppearance(root, { variants, seed: 1 });
    const shader = {
      uniforms: {} as Record<string, THREE.IUniform>,
      vertexShader: "#include <common>\n#include <begin_vertex>",
      fragmentShader: "#include <common>\n#include <color_fragment>\n#include <map_fragment>\n#include <dithering_fragment>"
    };
    (mesh.material as THREE.MeshStandardMaterial).onBeforeCompile(shader as THREE.WebGLProgramParametersWithUniforms, {} as THREE.WebGLRenderer);
    assert.match(shader.fragmentShader, /1\.0 - floor\(cVar \/ 3\.0\)/, "must flip Y row for 3x2 WebGL texture atlas");
    assert.match(shader.fragmentShader, /fract\(cUv\.y\)/, "must tile vertically with fract(cUv.y), never clamp");
    assert.match(shader.fragmentShader, /uComfyVariantMap/, "must bind per-building variant lookup texture");
    assert.match(shader.fragmentShader, /cComfyWindowGlow/, "must add night interior window glow on ComfyUI facades");
  });

  it("enhances Three.js wet ground material with micro-roughness specular contrast", () => {
    const mat = new THREE.MeshBasicMaterial();
    applyWetGroundShader(mat);
    const shader = {
      uniforms: {} as Record<string, THREE.IUniform>,
      vertexShader: "#include <common>\n#include <begin_vertex>",
      fragmentShader: "#include <common>\n#include <map_fragment>\n#include <dithering_fragment>"
    };
    mat.onBeforeCompile(shader as THREE.WebGLProgramParametersWithUniforms, {} as THREE.WebGLRenderer);
    assert.match(shader.fragmentShader, /wetPuddleMask/, "wet ground shader should modulate puddle specular contrast");
  });
});

describe("plateau-materials: glTF feature ids", () => {
  it("aliases _FEATURE_ID_0 to _batchid so the batch-id shaders keep working", () => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(9), 3));
    geometry.setAttribute("_FEATURE_ID_0", new THREE.BufferAttribute(new Float32Array(3), 1));
    const root = new THREE.Group();
    root.add(new THREE.Mesh(geometry, new THREE.MeshStandardMaterial()));
    applyPlateauBuildingAppearance(root, {});
    assert.ok(geometry.getAttribute("_batchid"));
    assert.equal(geometry.getAttribute("_batchid"), geometry.getAttribute("_FEATURE_ID_0"));
  });
});

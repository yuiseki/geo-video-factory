import * as THREE from 'three';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { MercatorCoordinate, type Map as MapLibre, type CustomLayerInterface, type CustomRenderMethodInput } from 'maplibre-gl';
import type { PlateauBuildingsConfig } from '../types.js';
import { tileHeightOffset, wgs84Ecef } from './plateau-coordinates.js';
import { applyBuildingAppearance, neutralizePbr } from './plateau-materials.js';
import { createPlateauRoofUniforms } from './plateau-facade-glsl.js';
import { createCityProxyMaterial, createCityShadowMaterial, createCityUniforms, type CityRoofPhoto, type CityUniforms } from './city-materials.js';
import { cityLight, keyframeValue, localMeters, paintRadius, revealRadius } from './city-timeline.js';

interface ModelTile {
  glb: string;
  kind?: string;
  /** 'enu': positions are local east/up/south meters around the manifest center (city-proxy). */
  frame?: string;
  /** Aerial photo draped on city-proxy roofs. */
  roof_texture?: { image: string; bounds_m: [number, number, number, number] };
  rtc: [number, number, number];
  bytes?: number;
  ids?: string[];
  facade_colors?: (string | null)[];
}

interface ModelManifest {
  format: 'geo-video-factory.plateau-3d/1';
  center?: [number, number];
  /** Aerial photo for the roofs of untextured PLATEAU buildings, in local meters around center. */
  roof_texture?: { image: string; bounds_m: [number, number, number, number] };
  tiles: ModelTile[];
}

export interface PlateauRenderStats {
  loadedTiles: number;
  totalTiles: number;
  triangles: number;
  drawCalls: number;
  objectCount: number;
}

function rowBasis(longitude: number, latitude: number): THREE.Matrix4 {
  const lambda = longitude * Math.PI / 180;
  const phi = latitude * Math.PI / 180;
  const east = [-Math.sin(lambda), Math.cos(lambda), 0];
  const north = [-Math.sin(phi) * Math.cos(lambda), -Math.sin(phi) * Math.sin(lambda), Math.cos(phi)];
  const up = [Math.cos(phi) * Math.cos(lambda), Math.cos(phi) * Math.sin(lambda), Math.sin(phi)];
  return new THREE.Matrix4().set(
    east[0]!, east[1]!, east[2]!, 0,
    north[0]!, north[1]!, north[2]!, 0,
    up[0]!, up[1]!, up[2]!, 0,
    0, 0, 0, 1,
  );
}

function yUpToZUp(): THREE.Matrix4 {
  return new THREE.Matrix4().set(1, 0, 0, 0, 0, 0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1);
}

async function readManifest(path: string): Promise<{ manifest: ModelManifest; url: URL }> {
  const url = new URL(path, window.location.origin + '/');
  const response = await fetch(url);
  if (!response.ok) throw new Error(`PLATEAU manifest ${response.status}: ${url}`);
  const manifest = await response.json() as ModelManifest;
  if (manifest.format !== 'geo-video-factory.plateau-3d/1' || !Array.isArray(manifest.tiles)) {
    throw new Error('unsupported PLATEAU buildings manifest format');
  }
  if (!manifest.tiles.length) throw new Error('PLATEAU buildings manifest has no tiles');
  return { manifest, url };
}

function batchUntexturedMeshes(root: THREE.Object3D): void {
  root.updateMatrixWorld(true);
  const identity = new THREE.Matrix4();
  const candidates: THREE.Mesh[] = [];
  root.traverse((object) => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh || Array.isArray(mesh.material)) return;
    const mat = mesh.material as THREE.MeshStandardMaterial;
    if (!mat || mat.map) return;
    if (!mesh.geometry.attributes.position || !mesh.geometry.attributes._batchid) return;
    candidates.push(mesh);
  });
  if (candidates.length <= 16) return;
  const geometries: THREE.BufferGeometry[] = [];
  for (const mesh of candidates) {
    const src = mesh.geometry;
    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position', src.attributes.position!.clone());
    if (src.attributes.normal) geom.setAttribute('normal', src.attributes.normal.clone());
    geom.setAttribute('_batchid', src.attributes._batchid!.clone());
    if (src.index) geom.setIndex(src.index.clone());
    if (!mesh.matrixWorld.equals(identity)) geom.applyMatrix4(mesh.matrixWorld);
    geometries.push(geom);
  }
  const merged = mergeGeometries(geometries, false);
  for (const geom of geometries) geom.dispose();
  if (!merged) return;
  for (const mesh of candidates) {
    mesh.parent?.remove(mesh);
    mesh.geometry.dispose();
    (mesh.material as THREE.Material).dispose();
  }
  root.add(new THREE.Mesh(merged, new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.92, metalness: 0 })));
}

function tuneMaterials(root: THREE.Object3D): void {
  root.traverse((object) => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh) return;
    mesh.frustumCulled = false;
    mesh.castShadow = false;
    mesh.receiveShadow = false;
    for (const material of (Array.isArray(mesh.material) ? mesh.material : [mesh.material])) {
      if (!material) continue;
      material.side = THREE.DoubleSide;
      neutralizePbr(material);
    }
  });
}

export interface PlateauBuildingsLayer {
  stats: () => PlateauRenderStats;
  /** Apply the time-driven reveal and lighting for the frame at `sec`. */
  update: (sec: number) => void;
}

interface BuildingGroup {
  scene: THREE.Scene;
  localToMercator: THREE.Matrix4;
  lights: { ambient: THREE.AmbientLight; sun: THREE.DirectionalLight; fill: THREE.DirectionalLight };
  city: CityUniforms;
  config: PlateauBuildingsConfig;
  totalTiles: number;
  loadedTiles: () => number;
}

/** One manifest: its own origin, lights and wave uniforms, so several cities can share a render. */
async function loadGroup(config: PlateauBuildingsConfig): Promise<BuildingGroup> {
  const { manifest, url } = await readManifest(config.manifest);
  if (!manifest.center) throw new Error('PLATEAU manifest must define a WGS84 center');
  const center = manifest.center;
  const origin = wgs84Ecef([center[0], center[1], 0]);
  const phi = center[1] * Math.PI / 180;
  const lambda = center[0] * Math.PI / 180;
  const east = [-Math.sin(lambda), Math.cos(lambda), 0];
  const north = [-Math.sin(phi) * Math.cos(lambda), -Math.sin(phi) * Math.sin(lambda), Math.cos(phi)];
  const up = [Math.cos(phi) * Math.cos(lambda), Math.cos(phi) * Math.sin(lambda), Math.sin(phi)];
  const dot = (a: number[], b: number[]) => a[0]! * b[0]! + a[1]! * b[1]! + a[2]! * b[2]!;
  const scene = new THREE.Scene();
  const ambient = new THREE.AmbientLight(0xffffff, 1.15);
  scene.add(ambient);
  const sun = new THREE.DirectionalLight(0xfff4e6, 0.85);
  // Ground shadows are baked for this sun (packages/pipeline/city_proxy.py SHADOW_PER_M).
  sun.position.set(-300, -450, 450);
  scene.add(sun);
  const fill = new THREE.DirectionalLight(0xdce8ff, 0.35);
  fill.position.set(300, 200, 400);
  scene.add(fill);
  const city = createCityUniforms();
  const roofUniforms = createPlateauRoofUniforms();
  const growOrigin = config.reveal ? localMeters(config.reveal.center, center) : [0, 0];
  city.uCityGrowOrigin.value.set(growOrigin[0]!, growOrigin[1]!);
  city.uCityGrowWidth.value = config.reveal?.width ?? 120;
  const draco = new DRACOLoader().setDecoderPath('/node_modules/three/examples/jsm/libs/draco/').setWorkerLimit(2);
  const loader = new GLTFLoader().setDRACOLoader(draco);
  const originMercator = MercatorCoordinate.fromLngLat(center, 0);
  const meterScale = originMercator.meterInMercatorCoordinateUnits();
  const localToMercator = new THREE.Matrix4()
    .makeTranslation(originMercator.x, originMercator.y, originMercator.z)
    .multiply(new THREE.Matrix4().makeScale(meterScale, -meterScale, meterScale));
  const yToZ = yUpToZUp();
  const basis = rowBasis(center[0], center[1]);
  const heightOffset = config.heightOffset ?? 0;
  const workerCount = Math.max(1, Math.min(8, Math.floor(config.workers ?? 3)));
  const loadPhoto = async (image: string) => {
    const texture = await new THREE.TextureLoader().loadAsync(new URL(image, url).href);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = 8;
    return texture;
  };
  if (manifest.roof_texture && config.appearance !== false) {
    const [x0, y0, x1, y1] = manifest.roof_texture.bounds_m;
    roofUniforms.uPlateauRoofPhoto.value = await loadPhoto(manifest.roof_texture.image);
    roofUniforms.uPlateauRoofMin.value.set(x0, y0);
    roofUniforms.uPlateauRoofSize.value.set(x1 - x0, y1 - y0);
    roofUniforms.uPlateauRoofOn.value = 1;
  }
  let cursor = 0;
  let loadedTiles = 0;
  const loadWorker = async () => {
    while (cursor < manifest.tiles.length) {
      const tile = manifest.tiles[cursor++]!;
      const modelUrl = new URL(tile.glb, url).href;
      const gltf = await loader.loadAsync(modelUrl);
      batchUntexturedMeshes(gltf.scene);
      const delta = tile.rtc.map((value, index) => value - origin[index]!) as [number, number, number];
      const localPosition: [number, number, number] = [dot(east, delta), dot(north, delta), dot(up, delta) + tileHeightOffset(tile.kind, heightOffset)];
      const translate = new THREE.Matrix4().makeTranslation(...localPosition);
      gltf.scene.matrixAutoUpdate = false;
      if (tile.frame === 'enu') {
        gltf.scene.matrix.copy(yToZ);
      } else {
        gltf.scene.matrix.copy(translate).multiply(basis).multiply(yToZ);
      }
      tuneMaterials(gltf.scene);
      if (tile.kind === 'city-proxy' || tile.kind === 'city-shadow') {
        let roof: CityRoofPhoto | undefined;
        if (tile.kind === 'city-proxy' && tile.roof_texture) {
          roof = { texture: await loadPhoto(tile.roof_texture.image), bounds: tile.roof_texture.bounds_m };
        }
        const material = tile.kind === 'city-proxy' ? createCityProxyMaterial(roof, city) : createCityShadowMaterial(city);
        gltf.scene.traverse((object) => {
          const mesh = object as THREE.Mesh;
          if (mesh.isMesh) mesh.material = material;
        });
      } else if (config.appearance !== false) {
        // No building is left flat: photo textures stay, untextured buildings get a facade and the
        // aerial photo on their roofs as the paint wave passes. appearance: false is untouched PLATEAU.
        applyBuildingAppearance(gltf.scene, tile.facade_colors ?? (tile.ids ?? []).map(() => null), modelUrl, true, { city, roof: roofUniforms });
      }
      scene.add(gltf.scene);
      loadedTiles++;
    }
  };
  try {
    await Promise.all(Array.from({ length: workerCount }, loadWorker));
  } finally {
    draco.dispose();
  }
  return { scene, localToMercator, lights: { ambient, sun, fill }, city, config, totalTiles: manifest.tiles.length, loadedTiles: () => loadedTiles };
}

export async function addPlateauBuildings(
  map: MapLibre,
  configs: PlateauBuildingsConfig | PlateauBuildingsConfig[],
): Promise<PlateauBuildingsLayer> {
  const list = Array.isArray(configs) ? configs : [configs];
  const groups = await Promise.all(list.map((config) => loadGroup(config)));
  let renderer: THREE.WebGLRenderer | undefined;
  const camera = new THREE.Camera();
  const layer: CustomLayerInterface = {
    id: 'plateau-buildings-3d',
    type: 'custom',
    renderingMode: '3d',
    onAdd: (_map, gl) => {
      renderer = new THREE.WebGLRenderer({ canvas: map.getCanvas(), context: gl, antialias: true });
      renderer.autoClear = false;
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 0.82;
    },
    render: (_gl, args: CustomRenderMethodInput) => {
      if (!renderer) return;
      const projection = args.defaultProjectionData.mainMatrix as unknown as number[];
      renderer.resetState();
      for (const group of groups) {
        camera.projectionMatrix.fromArray(projection).multiply(group.localToMercator);
        renderer.render(group.scene, camera);
      }
    },
    onRemove: () => {
      renderer?.dispose();
      renderer = undefined;
    },
  };
  const styleLayers = map.getStyle().layers ?? [];
  const firstSymbol = styleLayers.find((item) => item.type === 'symbol')?.id;
  map.addLayer(layer, firstSymbol);
  const rasterLayers = styleLayers.filter((item) => item.type === 'raster').map((item) => item.id);
  const nightKeys = list.find((config) => config.night)?.night;
  const update = (sec: number) => {
    for (const group of groups) {
      group.city.uCityGrowRadius.value = revealRadius(group.config.reveal, sec);
      group.city.uCityPaintRadius.value = paintRadius(group.config.reveal, sec);
    }
    if (!nightKeys) return;
    const night = keyframeValue(nightKeys, sec);
    const light = cityLight(night);
    for (const group of groups) {
      const { ambient, sun, fill } = group.lights;
      ambient.intensity = light.ambient;
      ambient.color.setRGB(...light.ambientColor);
      sun.intensity = light.sun;
      sun.color.setRGB(...light.sunColor);
      fill.intensity = 0.35 * (1 - 0.7 * night);
      group.city.uCityWindows.value = light.windows;
      group.city.uCityShadow.value = light.shadow;
      group.city.uCityNight.value = night;
    }
    for (const id of rasterLayers) {
      map.setPaintProperty(id, 'raster-brightness-max', light.mapBrightness);
      map.setPaintProperty(id, 'raster-saturation', light.mapSaturation);
    }
    map.triggerRepaint();
  };
  return {
    update,
    stats: () => ({
      loadedTiles: groups.reduce((sum, group) => sum + group.loadedTiles(), 0),
      totalTiles: groups.reduce((sum, group) => sum + group.totalTiles, 0),
      triangles: renderer?.info.render.triangles ?? 0,
      drawCalls: renderer?.info.render.calls ?? 0,
      objectCount: groups.reduce((sum, group) => sum + group.scene.children.length, 0),
    }),
  };
}

import * as THREE from 'three';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { MercatorCoordinate, type Map as MapLibre, type CustomLayerInterface, type CustomRenderMethodInput } from 'maplibre-gl';
import type { PlateauBuildingsConfig } from '../types.js';
import { tileHeightOffset, wgs84Ecef } from './plateau-coordinates.js';
import { applyBuildingAppearance, neutralizePbr, plateauRoofUniforms } from './plateau-materials.js';
import { cityUniforms, createCityProxyMaterial, createCityShadowMaterial, type CityRoofPhoto } from './city-materials.js';
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

export async function addPlateauBuildings(map: MapLibre, config: PlateauBuildingsConfig): Promise<PlateauBuildingsLayer> {
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
  const fillBase = fill.intensity;
  fill.position.set(300, 200, 400);
  scene.add(fill);
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
  if (manifest.roof_texture && config.appearance !== false) {
    const texture = await new THREE.TextureLoader().loadAsync(new URL(manifest.roof_texture.image, url).href);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = 8;
    const [x0, y0, x1, y1] = manifest.roof_texture.bounds_m;
    plateauRoofUniforms.uPlateauRoofPhoto.value = texture;
    plateauRoofUniforms.uPlateauRoofMin.value.set(x0, y0);
    plateauRoofUniforms.uPlateauRoofSize.value.set(x1 - x0, y1 - y0);
    plateauRoofUniforms.uPlateauRoofOn.value = 1;
  }
  let cursor = 0;
  let loadedTiles = 0;
  const loadWorker = async () => {
    while (cursor < manifest.tiles.length) {
      const tile = manifest.tiles[cursor++]!;
      const modelUrl = new URL(tile.glb, url).href;
      const gltf = await loader.loadAsync(modelUrl);
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
          const texture = await new THREE.TextureLoader().loadAsync(new URL(tile.roof_texture.image, url).href);
          texture.colorSpace = THREE.SRGBColorSpace;
          texture.anisotropy = 8;
          roof = { texture, bounds: tile.roof_texture.bounds_m };
        }
        const material = tile.kind === 'city-proxy' ? createCityProxyMaterial(roof) : createCityShadowMaterial();
        gltf.scene.traverse((object) => {
          const mesh = object as THREE.Mesh;
          if (mesh.isMesh) mesh.material = material;
        });
      } else if (config.appearance !== false) {
        // The enhanced render leaves no building flat: photo textures stay, untextured buildings
        // get a facade and the aerial photo on their roofs. appearance: false is the untouched
        // "before" reference of a comparison.
        applyBuildingAppearance(gltf.scene, tile.facade_colors ?? (tile.ids ?? []).map(() => null), modelUrl);
      }
      scene.add(gltf.scene);
      loadedTiles++;
    }
  };
  try {
    await Promise.all(Array.from({ length: workerCount }, loadWorker));
  } catch (error) {
    draco.dispose();
    throw error;
  }
  draco.dispose();

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
      const projection = args.defaultProjectionData.mainMatrix;
      camera.projectionMatrix.fromArray(projection as unknown as number[]).multiply(localToMercator);
      renderer.resetState();
      renderer.render(scene, camera);
    },
    onRemove: () => {
      renderer?.dispose();
      renderer = undefined;
    },
  };
  const styleLayers = map.getStyle().layers ?? [];
  const firstSymbol = styleLayers.find((item) => item.type === 'symbol')?.id;
  map.addLayer(layer, firstSymbol);
  const growOrigin = config.reveal ? localMeters(config.reveal.center, center) : [0, 0];
  cityUniforms.uCityGrowOrigin.value.set(growOrigin[0]!, growOrigin[1]!);
  cityUniforms.uCityGrowWidth.value = config.reveal?.width ?? 120;
  const rasterLayers = styleLayers.filter((item) => item.type === 'raster').map((item) => item.id);
  const update = (sec: number) => {
    cityUniforms.uCityGrowRadius.value = revealRadius(config.reveal, sec);
    cityUniforms.uCityPaintRadius.value = paintRadius(config.reveal, sec);
    if (!config.night) return;
    const night = keyframeValue(config.night, sec);
    const light = cityLight(night);
    ambient.intensity = light.ambient;
    ambient.color.setRGB(...light.ambientColor);
    sun.intensity = light.sun;
    sun.color.setRGB(...light.sunColor);
    fill.intensity = fillBase * (1 - 0.7 * night);
    cityUniforms.uCityWindows.value = light.windows;
    cityUniforms.uCityShadow.value = light.shadow;
    cityUniforms.uCityNight.value = night;
    for (const id of rasterLayers) {
      map.setPaintProperty(id, 'raster-brightness-max', light.mapBrightness);
      map.setPaintProperty(id, 'raster-saturation', light.mapSaturation);
    }
    map.triggerRepaint();
  };
  return {
    update,
    stats: () => ({
      loadedTiles,
      totalTiles: manifest.tiles.length,
      triangles: renderer?.info.render.triangles ?? 0,
      drawCalls: renderer?.info.render.calls ?? 0,
      objectCount: scene.children.length,
    }),
  };
}

import * as THREE from 'three';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { MercatorCoordinate, type Map as MapLibre, type CustomLayerInterface, type CustomRenderMethodInput } from 'maplibre-gl';
import type { PlateauBuildingsConfig } from '../types.js';
import { tileHeightOffset, wgs84Ecef } from './plateau-coordinates.js';
import { applyBuildingAppearance } from './plateau-materials.js';

interface ModelTile {
  glb: string;
  kind?: string;
  rtc: [number, number, number];
  bytes?: number;
  ids?: string[];
  facade_colors?: (string | null)[];
}

interface ModelManifest {
  format: 'geo-video-factory.plateau-3d/1';
  center?: [number, number];
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
      if (material instanceof THREE.MeshStandardMaterial) {
        material.roughness = Math.max(material.roughness, 0.72);
        material.metalness = Math.min(material.metalness, 0.08);
      }
    }
  });
}

export async function addPlateauBuildings(map: MapLibre, config: PlateauBuildingsConfig): Promise<() => PlateauRenderStats> {
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
  scene.add(new THREE.AmbientLight(0xffffff, 1.15));
  const sun = new THREE.DirectionalLight(0xffffff, 0.72);
  sun.position.set(-200, -300, 700);
  scene.add(sun);
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
      gltf.scene.matrix.copy(translate).multiply(basis).multiply(yToZ);
      tuneMaterials(gltf.scene);
      applyBuildingAppearance(gltf.scene, tile.facade_colors ?? (tile.ids ?? []).map(() => null), modelUrl);
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
  return () => ({
    loadedTiles,
    totalTiles: manifest.tiles.length,
    triangles: renderer?.info.render.triangles ?? 0,
    drawCalls: renderer?.info.render.calls ?? 0,
    objectCount: scene.children.length,
  });
}

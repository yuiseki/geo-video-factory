// Browser entry point: coordinates map setup and deterministic frame rendering.
import * as maplibregl from 'maplibre-gl';
import { cameraAt, locate } from '../lib.js';
import type { CameraKey, Shot, ShotSpec } from '../types.js';
import { buildMapStyle } from './map-style.js';
import { registerMapProtocols } from './map-protocols.js';
import type { MapLibreMap } from './map-types.js';
import { preloadChoroplethLabels } from './choropleth-dom.js';
import { configureOverlayRenderer, drawOverlays, setOverlayTime } from './overlays.js';
import { addPlateauBuildings, type PlateauBuildingsLayer } from './plateau-buildings.js';

let map: MapLibreMap;
let spec: ShotSpec;
let overlayEl: HTMLElement;
let buildings: PlateauBuildingsLayer | undefined;

function settle(timeoutMs = 40000): Promise<'idle' | 'timeout'> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve('timeout'), timeoutMs);
    map.once('idle', () => {
      clearTimeout(timer);
      resolve('idle');
    });
    map.triggerRepaint();
  });
}

function keysOf(shot: Shot): CameraKey[] {
  if (shot.keys) return shot.keys;
  const from = shot.from ?? shot.to!;
  const to = shot.to ?? shot.from!;
  return [{ t: 0, ...from }, { t: 1, ...to }];
}

const scale = () => (spec.width ?? 1920) / 1920;

async function init(s: ShotSpec): Promise<'idle' | 'timeout'> {
  spec = s;
  overlayEl = document.getElementById('overlay')!;
  const tintEl = document.getElementById('tint')!;
  const stage = document.getElementById('stage')!;
  stage.style.transform = `scale(${scale()})`;
  const mapEl = document.getElementById('map')!;
  Object.assign(mapEl.style, {
    width: (spec.width ?? 1920) + 'px',
    height: (spec.height ?? 1080) + 'px',
    transform: `scale(${1 / scale()})`,
    transformOrigin: '0 0',
  });
  if (spec.layer === 'map') {
    // the picture only: decorations are rendered as their own layer and laid over at the end
    for (const id of ['overlay', 'tint', 'credit']) document.getElementById(id)!.style.display = 'none';
  } else if (spec.layer === 'overlay') {
    document.documentElement.style.background = 'transparent';
    document.body.style.background = 'transparent';
    stage.style.background = 'transparent';
    mapEl.style.visibility = 'hidden';
  }
  registerMapProtocols();
  const style = buildMapStyle(spec);
  document.getElementById('credit')!.textContent = [...style.credits, ...(spec.credits ?? [])].join('\n');
  const { credits: _credits, ...mapStyle } = style;
  const first = cameraAt(keysOf(spec.shots[0]!), 0);
  map = new maplibregl.Map({
    container: 'map',
    style: mapStyle as unknown as maplibregl.StyleSpecification,
    center: first.center,
    zoom: first.zoom + (spec.zoomOffset ?? 0),
    pitch: first.pitch,
    bearing: first.bearing,
    maxPitch: 85,
    interactive: false,
    fadeDuration: 0,
    attributionControl: false,
    canvasContextAttributes: { preserveDrawingBuffer: true, antialias: true },
    pixelRatio: 1,
  }) as unknown as MapLibreMap;
  if (spec.fov !== undefined) {
    map.setVerticalFieldOfView(spec.fov);
  }
  if (spec.cameraPadding) {
    const padding = spec.cameraPadding;
    map.setPadding({
      top: (padding.top ?? 0) * scale(),
      right: (padding.right ?? 0) * scale(),
      bottom: (padding.bottom ?? 0) * scale(),
      left: (padding.left ?? 0) * scale(),
    });
  }
  configureOverlayRenderer({ map, spec, overlayEl, tintEl });
  await Promise.all([new Promise<void>((resolve) => map.once('load', resolve)), preloadChoroplethLabels(spec)]);
  if (spec.plateauBuildings) {
    buildings = await addPlateauBuildings(map as unknown as maplibregl.Map, spec.plateauBuildings);
  }
  return settle();
}

async function frame(sec: number): Promise<'idle' | 'timeout'> {
  setOverlayTime(sec);
  const { index, t } = locate(spec.shots, sec);
  const shot = spec.shots[index]!;
  const cam = cameraAt(keysOf(shot), t, shot.ease ?? 'inOut', {
    path: shot.path,
    curve: shot.curve,
    width: spec.width,
    height: spec.height,
  });
  map.jumpTo({ ...cam, zoom: cam.zoom + (spec.zoomOffset ?? 0) });
  buildings?.update(sec);
  drawOverlays(index, shot, t, 'map');
  const result = await settle();
  drawOverlays(index, shot, t, 'dom');
  await Promise.all([...overlayEl.querySelectorAll('img')].map((image) => image.decode().catch(() => console.error('panel image failed: ' + image.src))));
  return result;
}

function totalSeconds(): number {
  return spec.shots.reduce((sum, shot) => sum + (shot.duration ?? 0), 0);
}

(window as unknown as Record<string, unknown>).FLY = { init, frame, totalSeconds, get map() { return map; }, get plateauStats() { return buildings?.stats(); } };
(window as unknown as Record<string, unknown>).FLY_READY = true;

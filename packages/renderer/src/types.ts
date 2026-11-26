import type { CityReveal } from './page/city-timeline.js';
export type LngLat = [number, number];
export type EaseKind = 'linear' | 'smooth' | 'in' | 'out' | 'inOut';
export type CameraPathKind = 'linear' | 'fly';
export type TimeWindow = [number, number];

export interface CameraPose {
  center: LngLat;
  zoom: number;
  pitch?: number;
  bearing?: number;
}

export interface CameraKey extends CameraPose {
  t: number;
}

export type TtsEngine = 'voicevox' | 'openjtalk' | 'aquestalk';

export interface VoiceConfig {
  speaker?: number;
  engine?: TtsEngine;
  voice?: string;
  name?: string;
  speed?: number;
  pitch?: number;
  halfTone?: number;
  intonation?: number;
  volume?: number;
  htsvoice?: string;
  credit?: string;
  color?: string;
}

export interface OpenJTalkConfig {
  bin?: string;
  dic?: string;
  voice?: string;
}

export interface AquesTalkConfig {
  appDir?: string;
  python?: string;
}

export interface TtsConfig {
  engine?: TtsEngine;
  url?: string;
  openjtalk?: OpenJTalkConfig;
  aquestalk?: AquesTalkConfig;
  speed?: number;
  padStart?: number;
  pause?: number;
  padEnd?: number;
  wrap?: number;
  draftCps?: number;
}

export interface ReactionCharacter {
  sprites: string;
  seed?: string;
}

export interface ReactionConfig {
  characters?: Record<string, ReactionCharacter>;
  order?: string[];
  height?: number;
  side?: 'left' | 'right';
  margin?: number;
  bottom?: number;
}

export interface ReactionSegment {
  t0: number;
  t1: number;
  speaker: string;
  face: string;
  react: string;
  env: number[];
}

export interface LineSpec {
  voice?: string;
  text: string;
  speech?: string;
  face?: string;
  react?: string;
}

export interface BaseOverlay {
  type: 'base';
  layer: string;
  saturation?: number;
  show?: TimeWindow;
  fade?: number;
}

export interface ImageOverlay {
  type: 'image';
  src: string;
  bbox: [number, number, number, number];
  maxzoom?: number;
  credit?: string;
  show?: TimeWindow;
  fade?: number;
}

export interface LineOverlay {
  type: 'line';
  coords: LngLat[];
  color?: string;
  width?: number;
  draw?: TimeWindow;
  show?: TimeWindow;
  fade?: number;
}

export interface PolygonOverlay {
  type: 'polygon';
  coords: LngLat[];
  fill?: string;
  fillOpacity?: number;
  outline?: string;
  width?: number;
  show?: TimeWindow;
  fade?: number;
}

export interface LabelOverlay {
  type: 'label';
  text: string;
  /** Screen offset in 1920px design coordinates, applied after projecting `at`. */
  offset?: [number, number];
  /** Draw a leader from the projected location to the offset label. */
  leader?: boolean;
  at?: LngLat;
  screen?: [number, number];
  style?: string;
  color?: string;
  dot?: boolean;
  show?: TimeWindow;
  fade?: number;
}

export interface CounterOverlay {
  type: 'counter';
  value: number | string;
  from?: number;
  decimals?: number;
  grouping?: boolean;
  countUp?: TimeWindow;
  countEase?: 'linear' | 'out';
  /** Show the number as rolling odometer wheels while it counts. */
  roll?: boolean;
  caption?: string;
  prefix?: string;
  unit?: string;
  scale?: number;
  screen?: [number, number];
  show?: TimeWindow;
  fade?: number;
}

export interface ChapterOverlay {
  type: 'chapter';
  kicker?: string;
  text: string;
  show?: TimeWindow;
  fade?: number;
}

export interface NoteOverlay {
  type: 'note';
  text: string;
  show?: TimeWindow;
  fade?: number;
}

export interface QuoteOverlay {
  type: 'quote';
  text: string;
  source?: string;
  date?: string;
  marks?: boolean;
  cps?: number;
  width?: number;
  screen?: [number, number];
  show?: TimeWindow;
  fade?: number;
}

export interface PhotoMarkerOverlay {
  type: 'photo_marker';
  src: string;
  at: LngLat;
  caption?: string;
  credit?: string;
  screen?: [number, number];
  width?: number;
  height?: number;
  targetLabel?: string;
  cameraAt?: LngLat;
  cameraLabel?: string;
  cameraLabelAnchor?: 'start' | 'end';
  cameraLabelOffset?: [number, number];
  bridgeAt?: LngLat;
  bridgeLabel?: string;
  show?: TimeWindow;
  fade?: number;
}

export interface PanelOverlay {
  type: 'panel';
  src: string;
  caption?: string;
  credit?: string;
  screen?: [number, number];
  width?: number;
  height?: number;
  fullscreen?: boolean;
  expand?: TimeWindow;
  collapse?: TimeWindow;
  motion?: 'still' | 'in' | 'out' | 'up' | 'down';
  show?: TimeWindow;
  fade?: number;
}

export interface ChartOverlay {
  type: 'chart';
  points: [string, number][];
  width?: number;
  height?: number;
  ymin?: number;
  ymax?: number;
  decimals?: number;
  unit?: string;
  yticks?: number[];
  xlabels?: [string, number][];
  labels?: number[];
  drawSec?: number;
  caption?: string;
  credit?: string;
  screen?: [number, number];
  show?: TimeWindow;
  fade?: number;
}

export interface StickerOverlay {
  type: 'sticker';
  src: string;
  credit?: string;
  screen?: [number, number];
  width?: number;
  show?: TimeWindow;
  fade?: number;
}

export interface SubtitleOverlay {
  type: 'subtitle';
  text: string;
  color?: string;
  show?: TimeWindow;
  fade?: number;
}

export interface ReactionOverlay {
  type: 'reaction';
  segs: ReactionSegment[];
  show?: TimeWindow;
  fade?: number;
}

export interface ChoroplethLegend {
  title?: string;
  unit?: string;
  labels?: string[];
  position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
  showNoData?: boolean;
  noDataLabel?: string;
  valueDivisor?: number;
}

export interface ChoroplethFocus {
  property?: string;
  values: (string | number)[];
  window?: TimeWindow;
  dimOpacity?: number;
}

export interface ChoroplethOverlay {
  type: 'choropleth';
  src?: string;
  data?: unknown;
  property: string;
  breaks: number[];
  colors: string[];
  scale?: 'step' | 'linear';
  noDataColor?: string;
  opacity?: number;
  outline?: string;
  outlineWidth?: number;
  extrude?: boolean;
  heightProperty?: string;
  heightScale?: number;
  heightBase?: number;
  rise?: TimeWindow;
  focus?: ChoroplethFocus;
  legend?: boolean | ChoroplethLegend;
  labelProperty?: string;
  labelFontSize?: number;
  labelMaxFontSize?: number;
  credit?: string;
  show?: TimeWindow;
  fade?: number;
}

export interface HeatmapOverlay {
  type: 'heatmap';
  src?: string;
  data?: unknown;
  weightProperty?: string;
  radius?: number;
  intensity?: number;
  colors?: [number, string][];
  opacity?: number;
  credit?: string;
  show?: TimeWindow;
  fade?: number;
}

export type Overlay =
  | BaseOverlay
  | ImageOverlay
  | LineOverlay
  | PolygonOverlay
  | ChoroplethOverlay
  | HeatmapOverlay
  | LabelOverlay
  | CounterOverlay
  | ChapterOverlay
  | NoteOverlay
  | QuoteOverlay
  | PhotoMarkerOverlay
  | PanelOverlay
  | ChartOverlay
  | StickerOverlay
  | SubtitleOverlay
  | ReactionOverlay;

export interface Shot {
  duration?: number;
  from?: CameraPose;
  to?: CameraPose;
  keys?: CameraKey[];
  ease?: EaseKind;
  path?: CameraPathKind;
  curve?: number;
  tint?: number;
  subtitles?: boolean;
  lines?: LineSpec[];
  overlays?: Overlay[];
  digest?: boolean;
  transition?: boolean;
}

export interface BgmConfig {
  src: string;
  volume?: number;
}

export interface PlateauFacadeTextures {
  /** Upper-floor / curtain-wall facade texture (tiled in meters). */
  glass?: string;
  /** Ground-floor / shutter storefront texture (tiled in meters). */
  shutter?: string;
  /** Optional 3x2 building-facade atlas texture selected per building ID. */
  atlas?: string;
  /** Optional mapping from building ID (e.g. "bldg_...") to atlas cell index (0..5). */
  idVariants?: Record<string, number>;
  /** Blend factor onto building walls: 0..1 (defaults to 1 when provided). */
  wallMix?: number;
  /** World-space tile size in meters [width, height]. Defaults to [14, 14]. */
  tileMeters?: [number, number];
  /** Ground-floor base elevation in local Z meters. Defaults to 0. */
  groundZ?: number;
  /** Ground-floor shutter band height in meters. Defaults to 4.5. */
  shutterHeight?: number;
}

export interface BillboardConfig {
  /** Image path (project-root-relative or URL) for the cropped billboard/sign. */
  src: string;
  /** [lng, lat] of the billboard center on the building facade. */
  center: LngLat;
  /** Altitude of the billboard center in local Z meters (matching heightOffset). */
  altitudeM: number;
  /** Width of the billboard in meters. */
  widthM: number;
  /** Height of the billboard in meters. */
  heightM: number;
  /** Facing azimuth in degrees clockwise from north (0 = N, 90 = E, 180 = S, 270 = W). */
  bearing: number;
  /** Emissive night glow brightness multiplier (defaults to 1.0). */
  glow?: number;
}

export interface GroundPlaneConfig {
  /** Image path for high-res flat ground texture rendered in Three.js with anisotropic filtering. */
  src: string;
  /** [west, south, east, north] in WGS84 degrees. */
  bbox: [number, number, number, number];
  /** Local Z altitude in meters (defaults to 0.05). */
  altitudeM?: number;
  /** Brightness multiplier (defaults to 1.0). */
  brightness?: number;
}

export interface StreetPropConfig {
  kind: 'lamp' | 'signal' | 'arch' | 'wash' | 'kiosk';
  center: LngLat;
  altitudeM?: number;
  heightM?: number;
  widthM?: number;
  bearing?: number;
  color?: string;
}

export interface PlateauBuildingsConfig {
  /** URL or project-root-relative path to a geo-video-factory.plateau-3d/1 manifest. */
  manifest: string;
  /** Height offset applied to source ECEF buildings, in meters. Defaults to 0. */
  heightOffset?: number;
  /** Deterministic worker count for loading model assets. Defaults to 3. */
  workers?: number;
  /** Recolor buildings with the orthophoto palette. Defaults to true. The facade pattern is always applied. */
  appearance?: boolean;
  /**
   * Where the manifest's aerial roof photo goes: 'untextured' (default) only on buildings PLATEAU ships
   * without a texture; 'all' also on the upward faces of photo-textured ones (pale, coarse PLATEAU roofs).
   */
  roofPhoto?: 'untextured' | 'all';
  /** A sharper aerial photo (project-root path) of part of the area, [west, south, east, north]; the manifest's elsewhere. */
  roofPhotoNear?: { image: string; bbox: [number, number, number, number] };
  /** With roofPhoto 'all': photo-textured roofs above this height (scene metres) keep the PLATEAU photo. */
  roofPhotoMaxZ?: number;
  /** Optional ComfyUI/custom tileable facade textures mapped onto building walls in meters. */
  facadeTextures?: PlateauFacadeTextures;
  /** Optional 3D emissive billboard/sign planes placed on building facades. */
  billboards?: BillboardConfig[];
  /** Optional flat Three.js ground plane (avoids MapLibre raster oblique distortion & night desaturation). */
  groundPlane?: GroundPlaneConfig;
  /** Optional 3D street furniture (lamps, traffic signals, street arches) for human scale. */
  streetProps?: StreetPropConfig[];
  /** Buildings rise out of the ground in a wave from a point (city-proxy tiles). */
  reveal?: CityReveal;
  /** [seconds, 0..1] keys: 0 day, 0.5 dusk, 1 night with lit windows. */
  night?: [number, number][];
  /** Building opacity (0..1) or [seconds, 0..1] keyframes. Defaults to 1 (opaque). */
  opacity?: number | [number, number][];
}

export interface ShotSpec {
  width?: number;
  /** Reserved map margins in 1920px design coordinates, for example the subtitle band. */
  cameraPadding?: { top?: number; right?: number; bottom?: number; left?: number };
  height?: number;
  fps?: number;
  /** Vertical field of view in degrees (MapLibre default is ~36.87). */
  fov?: number;
  projection?: 'mercator' | 'globe' | 'vertical-perspective' | { type: string };
  base?: string;
  dem?: 'gsi' | 'mapterhorn' | string;
  exaggeration?: number;
  hillshade?: number | false;
  world?: string | false;
  worldFade?: [number, number];
  background?: string;
  saturation?: number;
  contrast?: number;
  sky?: Record<string, unknown>;
  osmLabels?: boolean;
  /** One manifest, or several (each with its own origin, reveal and roof photo) in one render. */
  plateauBuildings?: PlateauBuildingsConfig | PlateauBuildingsConfig[];
  /** Set by the renderer (--layer): 'map' without decorations, 'overlay' decorations only. */
  layer?: 'all' | 'map' | 'overlay';
  /** Set by the renderer when --size differs from the designed width, to keep the framing. */
  zoomOffset?: number;
  credits?: string[];
  voices?: Record<string, VoiceConfig>;
  tts?: TtsConfig;
  reaction?: ReactionConfig;
  bgm?: BgmConfig;
  subtitles?: boolean;
  shots: Shot[];
}

export interface DemConfig {
  tiles: string[];
  maxzoom: number;
  tileSize: number;
  credit: string;
}

export interface DemSourceSpec {
  source: {
    type: 'raster-dem';
    tiles: string[];
    tileSize: number;
    maxzoom: number;
    encoding: 'terrarium';
  };
  credit: string;
}

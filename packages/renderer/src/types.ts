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

export interface VoiceConfig {
  speaker: number;
  name?: string;
  speed?: number;
  pitch?: number;
  intonation?: number;
  volume?: number;
  color?: string;
}

export interface TtsConfig {
  url?: string;
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
  at?: LngLat;
  screen?: [number, number];
  style?: string;
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

export type Overlay =
  | BaseOverlay
  | ImageOverlay
  | LineOverlay
  | PolygonOverlay
  | ChoroplethOverlay
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

export interface PlateauBuildingsConfig {
  /** URL or project-root-relative path to a geo-video-factory.plateau-3d/1 manifest. */
  manifest: string;
  /** Height offset applied to source ECEF buildings, in meters. Defaults to 0. */
  heightOffset?: number;
  /** Deterministic worker count for loading model assets. Defaults to 3. */
  workers?: number;
  /** Recolor buildings with the orthophoto palette. Defaults to true. The facade pattern is always applied. */
  appearance?: boolean;
  /** Buildings rise out of the ground in a wave from a point (city-proxy tiles). */
  reveal?: CityReveal;
  /** [seconds, 0..1] keys: 0 day, 0.5 dusk, 1 night with lit windows. */
  night?: [number, number][];
}

export interface ShotSpec {
  width?: number;
  height?: number;
  fps?: number;
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

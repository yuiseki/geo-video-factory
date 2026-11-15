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

export type Overlay =
  | BaseOverlay
  | ImageOverlay
  | LineOverlay
  | PolygonOverlay
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
  plateauBuildings?: PlateauBuildingsConfig;
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

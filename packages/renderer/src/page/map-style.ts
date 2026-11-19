import { demSourceSpec } from '../lib.js';
import { choroplethColorExpression, choroplethFocusFilters, choroplethHeightExpression } from '../choropleth.js';
import { heatmapColorExpression, heatmapRadiusExpression, heatmapWeightExpression } from '../heatmap.js';
import type { Shot, ShotSpec } from '../types.js';
import { registerImageOverlay } from './map-protocols.js';

interface TileConfig {
  tiles: string[];
  minzoom?: number;
  maxzoom: number;
  credit: string;
}

const BASES: Record<string, TileConfig> = {
  // 地理院タイル 全国最新写真(シームレス)。世界の低ズームは衛星モザイクで埋まっている
  // the photo paints open sea black where there is no picture; gsiclear turns that black transparent
  seamlessphoto: {
    tiles: ['gsiclear://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg'],
    maxzoom: 18,
    credit: '空中写真：国土地理院(地理院タイル「全国最新写真(シームレス)」)を加工',
  },
  std: {
    tiles: ['https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png'],
    maxzoom: 18,
    credit: '地図：国土地理院(地理院タイル「標準地図」)を加工',
  },
  pale: {
    tiles: ['https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png'],
    maxzoom: 18,
    credit: '地図：国土地理院(地理院タイル「淡色地図」)を加工',
  },
  relief: {
    tiles: ['https://cyberjapandata.gsi.go.jp/xyz/relief/{z}/{x}/{y}.png'],
    minzoom: 5,
    maxzoom: 15,
    credit: '地図：国土地理院(地理院タイル「色別標高図」)を加工',
  },
  // 過去の空中写真。範囲と年代は場所ごとに違う。minzoom より引いたカメラでは何も出ない
  gazo1: {
    tiles: ['gsiclear://cyberjapandata.gsi.go.jp/xyz/gazo1/{z}/{x}/{y}.jpg'],
    minzoom: 10,
    maxzoom: 17,
    credit: '1974〜78年の空中写真：国土画像情報(カラー空中写真) 国土交通省 を加工',
  },
  ort_old10: {
    tiles: ['https://cyberjapandata.gsi.go.jp/xyz/ort_old10/{z}/{x}/{y}.png'],
    minzoom: 15,
    maxzoom: 17,
    credit: '1961〜69年の空中写真：国土地理院 を加工',
  },
  ort_USA10: {
    tiles: ['https://cyberjapandata.gsi.go.jp/xyz/ort_USA10/{z}/{x}/{y}.png'],
    minzoom: 15,
    maxzoom: 17,
    credit: '1945〜50年の空中写真：米軍撮影(国土地理院)を加工',
  },
  ort_riku10: {
    tiles: ['https://cyberjapandata.gsi.go.jp/xyz/ort_riku10/{z}/{x}/{y}.png'],
    minzoom: 15,
    maxzoom: 17,
    credit: '1936〜42年の空中写真：陸軍撮影(国土地理院)を加工',
  },
};

const rasterSource = (b: TileConfig) => ({
  type: 'raster',
  tiles: b.tiles,
  tileSize: 256,
  minzoom: b.minzoom ?? 0,
  maxzoom: b.maxzoom,
});

const WORLDS: Record<string, TileConfig> = {
  bluemarble: {
    tiles: ['https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg'],
    maxzoom: 8,
    credit: '衛星画像：NASA Blue Marble (海底地形つき、NASA GIBS 経由)',
  },
  'bluemarble-plain': {
    tiles: ['https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_NextGeneration/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg'],
    maxzoom: 8,
    credit: '衛星画像：NASA Blue Marble Next Generation (NASA GIBS 経由)',
  },
};

function overlayLayers(shots: Shot[]) {
  const sources: Record<string, unknown> = {};
  const layers: Record<string, unknown>[] = [];
  const baseLayers: Record<string, unknown>[] = [];
  const credits = new Set<string>();
  shots.forEach((s, si) =>
    (s.overlays || []).forEach((o, oi) => {
      const id = `ov-${si}-${oi}`;
      if (o.type === 'base') {
        const b = BASES[o.layer];
        if (!b) throw new Error(`unknown base layer: ${o.layer}`);
        sources['b-' + o.layer] = rasterSource(b);
        credits.add(b.credit);
        baseLayers.push({
          id,
          type: 'raster',
          source: 'b-' + o.layer,
          layout: { visibility: 'none' },
          paint: { 'raster-opacity': 0, 'raster-fade-duration': 0, 'raster-saturation': o.saturation ?? 0 },
        });
      } else if (o.type === 'image') {
        registerImageOverlay(id, '/' + o.src.replace(/^\/+/, ''), o.bbox);
        sources[id] = { type: 'raster', tiles: [`imgtile://${id}/{z}/{x}/{y}`], tileSize: 256, maxzoom: o.maxzoom ?? 18 };
        baseLayers.push({
          id,
          type: 'raster',
          source: id,
          layout: { visibility: 'none' },
          paint: { 'raster-opacity': 0, 'raster-fade-duration': 0 },
        });
        if (o.credit) credits.add(o.credit);
      } else if (o.type === 'line') {
        sources[id] = { type: 'geojson', data: { type: 'Feature', geometry: { type: 'LineString', coordinates: o.coords } } };
        layers.push({
          id: id + '-casing',
          type: 'line',
          source: id,
          layout: { 'line-cap': 'round', 'line-join': 'round', visibility: 'none' },
          paint: { 'line-color': '#ffffff', 'line-width': (o.width ?? 6) + 4, 'line-opacity': 0.9 },
        });
        layers.push({
          id,
          type: 'line',
          source: id,
          layout: { 'line-cap': 'round', 'line-join': 'round', visibility: 'none' },
          paint: { 'line-color': o.color ?? '#4aa3ff', 'line-width': o.width ?? 6 },
        });
      } else if (o.type === 'polygon') {
        sources[id] = { type: 'geojson', data: { type: 'Feature', geometry: { type: 'Polygon', coordinates: [o.coords] } } };
        layers.push({
          id: id + '-fill',
          type: 'fill',
          source: id,
          layout: { visibility: 'none' },
          paint: { 'fill-color': o.fill ?? '#4aa3ff', 'fill-opacity': o.fillOpacity ?? 0.35 },
        });
        layers.push({
          id,
          type: 'line',
          source: id,
          layout: { 'line-join': 'round', visibility: 'none' },
          paint: { 'line-color': o.outline ?? '#ffffff', 'line-width': o.width ?? 4 },
        });
      } else if (o.type === 'choropleth') {
        if (!o.src && !o.data) throw new Error('choropleth overlay requires src or data');
        sources[id] = { type: 'geojson', data: o.src ? '/' + o.src.replace(/^\/+/, '') : o.data };
        const colorExpr = choroplethColorExpression(o.property, o.breaks, o.colors, o.scale ?? 'step', o.noDataColor ?? '#6b7280');
        const focusProp = o.focus?.property ?? o.labelProperty ?? o.property;
        const filters = o.focus ? choroplethFocusFilters(focusProp, o.focus.values) : null;
        const variants = filters
          ? [{ suffix: '', filter: filters.dimFilter }, { suffix: '-focus', filter: filters.focusFilter }]
          : [{ suffix: '', filter: undefined as unknown[] | undefined }];
        for (const { suffix, filter } of variants) {
          const lid = id + suffix;
          const extra = filter ? { filter } : {};
          if (o.extrude) {
            const heightProp = o.heightProperty ?? o.property;
            layers.push({
              id: lid + '-fill',
              type: 'fill-extrusion',
              source: id,
              ...extra,
              layout: { visibility: 'none' },
              paint: {
                'fill-extrusion-color': colorExpr,
                'fill-extrusion-height': choroplethHeightExpression(heightProp, o.heightScale ?? 1, o.heightBase ?? 0, o.rise ? 0 : 1),
                'fill-extrusion-base': 0,
                'fill-extrusion-opacity': o.opacity ?? 0.85,
              },
            });
          } else {
            layers.push({
              id: lid + '-fill',
              type: 'fill',
              source: id,
              ...extra,
              layout: { visibility: 'none' },
              paint: { 'fill-color': colorExpr, 'fill-opacity': o.opacity ?? 0.78 },
            });
          }
          layers.push({
            id: lid,
            type: 'line',
            source: id,
            ...extra,
            layout: { 'line-join': 'round', visibility: 'none' },
            paint: { 'line-color': o.outline ?? '#ffffff', 'line-width': o.outlineWidth ?? 1.2 },
          });
        }
        if (o.credit) credits.add(o.credit);
      } else if (o.type === 'heatmap') {
        if (!o.src && !o.data) throw new Error('heatmap overlay requires src or data');
        sources[id] = { type: 'geojson', data: o.src ? '/' + o.src.replace(/^\/+/, '') : o.data };
        layers.push({
          id,
          type: 'heatmap',
          source: id,
          layout: { visibility: 'none' },
          paint: {
            'heatmap-weight': heatmapWeightExpression(o.weightProperty),
            'heatmap-intensity': o.intensity ?? 1.0,
            'heatmap-color': heatmapColorExpression(o.colors),
            'heatmap-radius': heatmapRadiusExpression(o.radius ?? 26),
            'heatmap-opacity': o.opacity ?? 0.85,
          },
        });
        if (o.credit) credits.add(o.credit);
      }
    }),
  );
  return { sources, layers, baseLayers, credits: [...credits] };
}

export function buildMapStyle(spec: ShotSpec) {
  const base = BASES[spec.base ?? 'seamlessphoto']!;
  const dem = demSourceSpec(spec.dem ?? 'gsi');
  const world = spec.world === false ? null : WORLDS[spec.world ?? 'bluemarble']!;
  const [wf0, wf1] = spec.worldFade ?? [5.5, 7];
  const gsiOpacity = world ? ['interpolate', ['linear'], ['zoom'], wf0, 0, wf1, 1] : 1;
  const ov = overlayLayers(spec.shots);
  return {
    version: 8,
    // Frames are rendered one by one. A paint property set for a frame must show in that frame:
    // with the default 300 ms fade the ground under the terrain stayed one frame behind.
    transition: { duration: 0, delay: 0 },
    ...(spec.projection
      ? { projection: typeof spec.projection === 'string' ? { type: spec.projection } : spec.projection }
      : {}),
    ...(spec.osmLabels ? { glyphs: 'https://tile.yuiseki.net/fonts/{fontstack}/{range}.pbf' } : {}),
    sources: {
      base: rasterSource(base),
      baselo: { ...rasterSource(base), maxzoom: Math.min(12, base.maxzoom) },
      ...(world ? { world: rasterSource(world) } : {}),
      dem: dem.source,
      demshade: { ...dem.source },
      ...(spec.osmLabels ? { osm: { type: 'vector', url: 'https://tile.yuiseki.net/data/v3.json' } } : {}),
      ...ov.sources,
    },
    layers: [
      { id: 'bg', type: 'background', paint: { 'background-color': spec.background ?? '#10243a' } },
      ...(world ? [{ id: 'world', type: 'raster', source: 'world', paint: { 'raster-fade-duration': 0 } }] : []),
      {
        id: 'baselo',
        type: 'raster',
        source: 'baselo',
        paint: {
          'raster-saturation': spec.saturation ?? -0.1,
          'raster-contrast': spec.contrast ?? 0.08,
          'raster-fade-duration': 0,
          'raster-opacity': gsiOpacity,
        },
      },
      {
        id: 'base',
        type: 'raster',
        source: 'base',
        paint: {
          'raster-saturation': spec.saturation ?? -0.1,
          'raster-contrast': spec.contrast ?? 0.08,
          'raster-fade-duration': 0,
          'raster-opacity': gsiOpacity,
        },
      },
      ...ov.baseLayers,
      ...(spec.hillshade === false
        ? []
        : [
            {
              id: 'shade',
              type: 'hillshade',
              source: 'demshade',
              paint: {
                'hillshade-exaggeration': spec.hillshade ?? 0.25,
                'hillshade-shadow-color': '#0a1020',
                'hillshade-highlight-color': '#ffffff',
              },
            },
          ]),
      ...(spec.osmLabels ? osmLabelLayers() : []),
      ...ov.layers,
    ],
    // 3D buildings carry true heights; exaggerated terrain would bury them.
    terrain: { source: 'dem', exaggeration: spec.exaggeration ?? (spec.plateauBuildings ? 1 : 1.3) },
    sky: spec.sky ?? {
      'sky-color': '#6f9fd6',
      'horizon-color': '#dce8f5',
      'fog-color': '#c9d8e8',
      'sky-horizon-blend': 0.6,
      'horizon-fog-blend': 0.7,
      'fog-ground-blend': 0.85,
      'atmosphere-blend': 0,
    },
    credits: [
      base.credit,
      ...(world ? [world.credit] : []),
      ...ov.credits,
      dem.credit,
      ...(spec.osmLabels ? ['地名：© OpenStreetMap contributors / OpenMapTiles（現代の地名）'] : []),
    ],
  };
}

function osmLabelLayers() {
  const text = ['coalesce', ['get', 'name:ja'], ['get', 'name'], ['get', 'name_en']];
  const layout = { 'text-field': text, 'text-font': ['Noto Sans Regular'], 'text-padding': 6, 'text-max-width': 10 };
  const paint = { 'text-color': '#ffffff', 'text-halo-color': 'rgba(10, 16, 28, 0.88)', 'text-halo-width': 2.5 };
  return [
    {
      id: 'osm-place',
      type: 'symbol',
      source: 'osm',
      'source-layer': 'place',
      minzoom: 9,
      filter: ['in', ['get', 'class'], ['literal', ['city', 'town', 'suburb', 'island']]],
      layout: { ...layout, 'text-size': ['interpolate', ['linear'], ['zoom'], 10, 16, 15, 22] },
      paint,
    },
    {
      id: 'osm-water',
      type: 'symbol',
      source: 'osm',
      'source-layer': 'waterway',
      minzoom: 12,
      layout: { ...layout, 'symbol-placement': 'line', 'text-size': 18 },
      paint,
    },
    {
      id: 'osm-station',
      type: 'symbol',
      source: 'osm',
      'source-layer': 'poi',
      minzoom: 13,
      filter: ['==', ['get', 'class'], 'rail'],
      layout: { ...layout, 'text-size': 18 },
      paint,
    },
  ];
}



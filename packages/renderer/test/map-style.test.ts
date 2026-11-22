import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildMapStyle } from '../src/page/map-style.js';

test('buildMapStyle passes projection when specified and omits it by default', () => {
  const baseSpec = { shots: [{ duration: 1, overlays: [] }] };
  const defaultStyle = buildMapStyle(baseSpec) as Record<string, unknown>;
  assert.equal('projection' in defaultStyle, false);

  const globeStyle = buildMapStyle({ ...baseSpec, projection: 'globe' }) as Record<string, unknown>;
  assert.deepEqual(globeStyle.projection, { type: 'globe' });

  const customStyle = buildMapStyle({ ...baseSpec, projection: { type: 'vertical-perspective' } }) as Record<string, unknown>;
  assert.deepEqual(customStyle.projection, { type: 'vertical-perspective' });
});

test('buildMapStyle turns off paint transitions: a frame shows its own time, not a wall-clock fade', () => {
  const style = buildMapStyle({ shots: [{ duration: 1, overlays: [] }] }) as Record<string, unknown>;
  assert.deepEqual(style.transition, { duration: 0, delay: 0 });
});

type Style = {
  sources: Record<string, Record<string, unknown>>;
  layers: Array<Record<string, any>>;
  credits: string[];
  terrain: { source: string; exaggeration: number };
  glyphs?: string;
};
const style = (spec: Record<string, unknown>) =>
  buildMapStyle({ shots: [{ duration: 1, overlays: [] }], ...spec } as never) as unknown as Style;
const ids = (s: Style) => s.layers.map((l) => l.id);
const shotWith = (...overlays: unknown[]) => ({ shots: [{ duration: 1, overlays }] });

test('buildMapStyle default layer stack is stable: bg, world, baselo, base, shade', () => {
  const s = style({});
  assert.deepEqual(ids(s), ['bg', 'world', 'baselo', 'base', 'shade']);
  assert.deepEqual(Object.keys(s.sources).sort(), ['base', 'baselo', 'dem', 'demshade', 'world']);
  assert.deepEqual(s.terrain, { source: 'dem', exaggeration: 1.3 });
});

test('buildMapStyle drops the world mosaic, hillshade and keeps opacity 1 when disabled', () => {
  const s = style({ world: false, hillshade: false });
  assert.deepEqual(ids(s), ['bg', 'baselo', 'base']);
  assert.equal(s.layers.find((l) => l.id === 'base')!.paint['raster-opacity'], 1);
  assert.equal('world' in s.sources, false);
});

test('buildMapStyle fades the photo in over the world mosaic with worldFade', () => {
  const s = style({ worldFade: [4, 6] });
  assert.deepEqual(s.layers.find((l) => l.id === 'base')!.paint['raster-opacity'], ['interpolate', ['linear'], ['zoom'], 4, 0, 6, 1]);
});

test('buildMapStyle caps the low-zoom base source at zoom 12 and exaggeration follows plateau buildings', () => {
  const s = style({});
  assert.equal(s.sources.baselo!.maxzoom, 12);
  assert.equal(s.sources.base!.maxzoom, 18);
  assert.equal(style({ plateauBuildings: { manifest: 'm.json' } }).terrain.exaggeration, 1);
  assert.equal(style({ plateauBuildings: { manifest: 'm.json' }, exaggeration: 2 }).terrain.exaggeration, 2);
});

test('buildMapStyle rejects unknown base layers and data-less choropleth/heatmap', () => {
  assert.throws(() => style(shotWith({ type: 'base', layer: 'nope' })), /unknown base layer: nope/);
  assert.throws(() => style(shotWith({ type: 'choropleth', property: 'p', breaks: [1, 2], colors: ['#fff', '#000'] })), /requires src or data/);
  assert.throws(() => style(shotWith({ type: 'heatmap' })), /requires src or data/);
});

test('buildMapStyle starts every overlay layer hidden with zero fade, so the page controls visibility per frame', () => {
  const s = style(
    shotWith(
      { type: 'base', layer: 'std' },
      { type: 'line', coords: [[0, 0], [1, 1]] },
      { type: 'polygon', coords: [[0, 0], [1, 0], [1, 1], [0, 0]] },
      { type: 'choropleth', src: '/a.geojson', property: 'p', breaks: [1, 2], colors: ['#fff', '#000'] },
      { type: 'heatmap', data: { type: 'FeatureCollection', features: [] } },
    ),
  );
  const overlay = s.layers.filter((l) => String(l.id).startsWith('ov-'));
  assert.ok(overlay.length >= 8);
  for (const l of overlay) assert.equal(l.layout.visibility, 'none', String(l.id));
  assert.equal(s.layers.find((l) => l.id === 'ov-0-0')!.paint['raster-opacity'], 0);
  assert.equal(s.layers.find((l) => l.id === 'ov-0-0')!.paint['raster-fade-duration'], 0);
});

test('buildMapStyle keeps raster overlays under hillshade and vector overlays above it', () => {
  const s = style(shotWith({ type: 'base', layer: 'std' }, { type: 'line', coords: [[0, 0], [1, 1]] }));
  const order = ids(s);
  assert.ok(order.indexOf('ov-0-0') < order.indexOf('shade'));
  assert.ok(order.indexOf('shade') < order.indexOf('ov-0-1-casing'));
  assert.ok(order.indexOf('ov-0-1-casing') < order.indexOf('ov-0-1'));
});

test('buildMapStyle shares one source per base layer and collects each credit once', () => {
  const s = style({
    shots: [
      { duration: 1, overlays: [{ type: 'base', layer: 'pale' }] },
      { duration: 1, overlays: [{ type: 'base', layer: 'pale' }, { type: 'base', layer: 'relief' }] },
    ],
  });
  assert.deepEqual(Object.keys(s.sources).filter((k) => k.startsWith('b-')).sort(), ['b-pale', 'b-relief']);
  assert.equal(s.credits.filter((c) => c.includes('淡色地図')).length, 1);
  assert.ok(s.credits.some((c) => c.includes('色別標高図')));
  assert.ok(s.credits[0]!.includes('国土地理院'));
});

test('buildMapStyle adds focus variants and extrusion for choropleth overlays', () => {
  const base = { type: 'choropleth', src: 'a.geojson', property: 'p', breaks: [1, 2], colors: ['#fff', '#000'] };
  const plain = style(shotWith(base));
  assert.deepEqual(ids(plain).filter((i) => String(i).startsWith('ov-')), ['ov-0-0-fill', 'ov-0-0']);
  assert.equal(plain.sources['ov-0-0']!.data, '/a.geojson');

  const focus = style(shotWith({ ...base, extrude: true, focus: { property: 'n', values: ['x'] } }));
  assert.deepEqual(ids(focus).filter((i) => String(i).startsWith('ov-')), ['ov-0-0-fill', 'ov-0-0', 'ov-0-0-focus-fill', 'ov-0-0-focus']);
  assert.equal(focus.layers.find((l) => l.id === 'ov-0-0-fill')!.type, 'fill-extrusion');
  assert.ok(focus.layers.find((l) => l.id === 'ov-0-0-focus')!.filter);
});

test('buildMapStyle osmLabels adds glyphs, an osm source, and three symbol layers', () => {
  const s = style({ osmLabels: true });
  assert.ok(s.glyphs);
  assert.ok(s.sources.osm);
  assert.deepEqual(ids(s).filter((i) => String(i).startsWith('osm-')), ['osm-place', 'osm-water', 'osm-station']);
  assert.ok(s.credits.some((c) => c.includes('OpenStreetMap')));
  assert.equal(style({}).glyphs, undefined);
});

test('buildMapStyle registers an image overlay as an imgtile raster source', () => {
  const s = style(shotWith({ type: 'image', src: '//assets/x.png', bbox: [0, 0, 1, 1], credit: 'c' }));
  assert.deepEqual(s.sources['ov-0-0']!.tiles, ['imgtile://ov-0-0/{z}/{x}/{y}']);
  assert.ok(s.credits.includes('c'));
});

test('buildMapStyle is deterministic and does not mutate its input', () => {
  const spec = { shots: [{ duration: 1, overlays: [{ type: 'line', coords: [[0, 0], [1, 1]] }] }] };
  const before = JSON.stringify(spec);
  assert.equal(JSON.stringify(buildMapStyle(spec as never)), JSON.stringify(buildMapStyle(spec as never)));
  assert.equal(JSON.stringify(spec), before);
});

// 性能の予算: 構造 (レイヤー数・ソース数) は描画コストに直結する。壁時計の閾値は余裕を大きく取る。
test('perf budget: default style stays small', () => {
  const s = style({});
  assert.ok(s.layers.length <= 5, `layers=${s.layers.length}`);
  assert.ok(Object.keys(s.sources).length <= 5, `sources=${Object.keys(s.sources).length}`);
});

test('perf budget: overlays add at most 2 layers each (4 for focused choropleth) and one source', () => {
  const n = 50;
  const overlays = Array.from({ length: n }, (_, i) => ({ type: 'line', coords: [[i, 0], [i, 1]] }));
  const s = style(shotWith(...overlays));
  assert.ok(s.layers.length - 5 <= 2 * n);
  assert.equal(Object.keys(s.sources).length - 5, n);
});

test('perf budget: building a 500-shot style takes well under a second', () => {
  const shots = Array.from({ length: 500 }, (_, i) => ({ duration: 1, overlays: [{ type: 'line', coords: [[i, 0], [i, 1]] }] }));
  const t0 = performance.now();
  buildMapStyle({ shots } as never);
  const ms = performance.now() - t0;
  assert.ok(ms < 1000, `buildMapStyle(500 shots) took ${ms.toFixed(0)} ms`);
});

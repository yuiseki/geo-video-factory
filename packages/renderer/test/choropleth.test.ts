import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildChoroplethLegendItems,
  choroplethColorExpression,
  choroplethDimMultiplier,
  choroplethExtrusionHeight,
  choroplethFocusFilters,
  choroplethHeightExpression,
  choroplethLabelFontSize,
  choroplethLabelOpacity,
  computeEqualBreaks,
  computeQuantileBreaks,
  extractChoroplethLabelPoints,
  extrusionScreenOffsetY,
} from '../src/choropleth.js';
import { buildMapStyle } from '../src/page/map-style.js';
import type { ShotSpec } from '../src/types.js';

test('choroplethColorExpression builds step expression and isolates NoData from numeric 0', () => {
  const expr = choroplethColorExpression('pop', [0, 100, 500], ['#eff3ff', '#6baed6', '#08519c'], 'step', '#555555');
  assert.deepEqual(expr, [
    'case',
    ['==', ['typeof', ['get', 'pop']], 'number'],
    ['step', ['get', 'pop'], '#eff3ff', 100, '#6baed6', 500, '#08519c'],
    '#555555',
  ]);
});

test('choroplethColorExpression builds linear interpolate expression and validates breaks/colors length', () => {
  const expr = choroplethColorExpression('diff', [-10, 0, 10], ['#2166ac', '#f7f7f7', '#b2182b'], 'linear', '#6b7280');
  assert.deepEqual(expr, [
    'case',
    ['==', ['typeof', ['get', 'diff']], 'number'],
    ['interpolate', ['linear'], ['get', 'diff'], -10, '#2166ac', 0, '#f7f7f7', 10, '#b2182b'],
    '#6b7280',
  ]);
  assert.throws(() => choroplethColorExpression('diff', [0, 10], ['#fff'], 'step'), /colors/i);
  assert.throws(() => choroplethColorExpression('diff', [10, 0], ['#fff', '#000'], 'step'), /ascending/i);
});

test('choroplethHeightExpression scales positive values and supports rise progress', () => {
  assert.deepEqual(choroplethHeightExpression('pop', 2, 0, 1), [
    'case',
    ['==', ['typeof', ['get', 'pop']], 'number'],
    ['max', 0, ['*', ['-', ['get', 'pop'], 0], 2]],
    0,
  ]);
  assert.deepEqual(choroplethHeightExpression('pop', 2, 100, 0.5), [
    'case',
    ['==', ['typeof', ['get', 'pop']], 'number'],
    ['max', 0, ['*', ['-', ['get', 'pop'], 100], 1]],
    0,
  ]);
});

test('computeQuantileBreaks and computeEqualBreaks ignore non-finite values', () => {
  assert.deepEqual(computeEqualBreaks([0, 25, 100, Number.NaN], 4), [0, 25, 50, 75]);
  assert.deepEqual(computeQuantileBreaks([10, 20, 30, 40, 50, 60, 70, 80], 4), [10, 27.5, 45, 62.5]);
});

test('buildMapStyle creates fill layer for 2D choropleth and fill-extrusion layer for 3D choropleth', () => {
  const spec: ShotSpec = {
    shots: [
      {
        duration: 4,
        from: { center: [139.75, 35.68], zoom: 11 },
        overlays: [
          {
            type: 'choropleth',
            src: 'data/wards.geojson',
            property: 'density',
            breaks: [0, 5000, 15000],
            colors: ['#fee5d9', '#fcae91', '#cb181d'],
            credit: '統計：テスト統計',
          },
          {
            type: 'choropleth',
            data: { type: 'FeatureCollection', features: [] },
            property: 'pop',
            breaks: [0, 100000, 300000],
            colors: ['#edf8e9', '#74c476', '#006d2c'],
            extrude: true,
            heightScale: 0.01,
          },
        ],
      },
    ],
  };

  const style = buildMapStyle(spec);
  const sources = style.sources as unknown as Record<string, { type: string; data?: unknown }>;
  assert.equal(sources['ov-0-0']?.type, 'geojson');
  assert.equal(sources['ov-0-0']?.data, '/data/wards.geojson');

  const layers = style.layers as Array<{ id: string; type: string; paint: Record<string, unknown> }>;
  const fill2d = layers.find((l) => l.id === 'ov-0-0-fill');
  const line2d = layers.find((l) => l.id === 'ov-0-0');
  assert.equal(fill2d?.type, 'fill');
  assert.equal(line2d?.type, 'line');

  const extrude3d = layers.find((l) => l.id === 'ov-0-1-fill');
  assert.equal(extrude3d?.type, 'fill-extrusion');
  assert.ok(Array.isArray(extrude3d?.paint['fill-extrusion-height']));
  assert.ok(style.credits.includes('統計：テスト統計'));
});

test('buildChoroplethLegendItems formats step ranges, custom labels, and NoData entry', () => {
  const autoItems = buildChoroplethLegendItems({
    breaks: [0, 250000, 550000],
    colors: ['#ffffb2', '#fd8d3c', '#bd0026'],
    unit: '万人',
    valueDivisor: 10000,
    showNoData: true,
    noDataColor: '#6b7280',
  });
  assert.deepEqual(autoItems, [
    { color: '#ffffb2', label: '0〜25万人' },
    { color: '#fd8d3c', label: '25〜55万人' },
    { color: '#bd0026', label: '55万人〜' },
    { color: '#6b7280', label: 'データなし' },
  ]);

  const customItems = buildChoroplethLegendItems({
    breaks: [0, 100],
    colors: ['#eff3ff', '#08519c'],
    labels: ['少ない', '多い'],
  });
  assert.deepEqual(customItems, [
    { color: '#eff3ff', label: '少ない' },
    { color: '#08519c', label: '多い' },
  ]);
});

test('extractChoroplethLabelPoints computes centroids (largest ring for MultiPolygon) and choroplethExtrusionHeight', () => {
  const fc = {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: { name: 'A区', pop: 500 },
        geometry: { type: 'Polygon', coordinates: [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]] },
      },
      {
        type: 'Feature',
        properties: { name: 'B区', pop: null },
        geometry: {
          type: 'MultiPolygon',
          coordinates: [
            [[[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5], [0, 0]]],
            [[[10, 10], [14, 10], [14, 14], [10, 14], [10, 10]]],
          ],
        },
      },
    ],
  };
  const pts = extractChoroplethLabelPoints(fc, 'name', 'pop');
  assert.equal(pts.length, 2);
  assert.deepEqual({ at: pts[0]!.at, text: pts[0]!.text, value: pts[0]!.value }, { at: [1, 1], text: 'A区', value: 500 });
  assert.deepEqual({ at: pts[1]!.at, text: pts[1]!.text, value: pts[1]!.value }, { at: [12, 12], text: 'B区', value: null });
  assert.deepEqual(pts[0]!.properties, { name: 'A区', pop: 500 });
  assert.equal(choroplethExtrusionHeight(500, 2, 100, 0.5), 400);
  assert.equal(choroplethExtrusionHeight(null, 2, 0, 1), 0);
  const dy = extrusionScreenOffsetY(7500, 35.68, 9.7, 55);
  assert.ok(dy < -60 && dy > -100, `expected upward screen offset around -80px, got ${dy}`);
  assert.equal(extrusionScreenOffsetY(0, 35.68, 9.7, 55), 0);
  assert.equal(choroplethLabelFontSize(500, 100, 900, 14, 30, 0), 14);
  assert.equal(choroplethLabelFontSize(500, 100, 900, 14, 30, 1), 22);
  assert.equal(choroplethLabelFontSize(900, 100, 900, 14, 30, 1), 30);
  assert.equal(choroplethLabelFontSize(null, 100, 900, 14, 30, 1), 14);
  assert.equal(choroplethLabelOpacity(1, 0, true), 0);
  assert.equal(choroplethLabelOpacity(0.8, 0.5, true), 0.4);
  assert.equal(choroplethLabelOpacity(1, 0, false), 1);
  assert.equal(choroplethLabelOpacity(1, 1, true, 900, 100, 900), 1);
  assert.equal(choroplethLabelOpacity(1, 1, true, 100, 100, 900), 0.35);
  assert.ok(Math.abs(choroplethLabelOpacity(1, 1, true, 500, 100, 900) - 0.675) < 1e-9);
});

test('choroplethDimMultiplier, choroplethFocusFilters and buildMapStyle split focus layers', () => {
  assert.equal(choroplethDimMultiplier(0, [0.1, 0.5], 0.15), 1);
  assert.ok(Math.abs(choroplethDimMultiplier(0.3, [0.1, 0.5], 0.2) - 0.6) < 1e-9);
  assert.equal(choroplethDimMultiplier(0.6, [0.1, 0.5], 0.15), 0.15);
  assert.equal(choroplethDimMultiplier(0, [-1, 0], 0.15), 0.15);

  const { focusFilter, dimFilter } = choroplethFocusFilters('name', ['東京都']);
  assert.deepEqual(focusFilter, ['in', ['get', 'name'], ['literal', ['東京都']]]);
  assert.deepEqual(dimFilter, ['!', ['in', ['get', 'name'], ['literal', ['東京都']]]]);

  const spec: ShotSpec = {
    base: 'pale',
    shots: [
      {
        duration: 3,
        from: { center: [139.74, 35.67], zoom: 4.5, pitch: 45, bearing: 0 },
        to: { center: [139.74, 35.67], zoom: 4.5, pitch: 45, bearing: 0 },
        overlays: [
          {
            type: 'choropleth',
            src: 'japan-pref-population.geojson',
            property: 'population',
            labelProperty: 'name',
            breaks: [0, 1000000],
            colors: ['#ffffb2', '#bd0026'],
            extrude: true,
            focus: { values: ['東京都'], window: [0.1, 0.5], dimOpacity: 0.15 },
          },
        ],
      },
    ],
  };
  const style = buildMapStyle(spec);
  const layers = style.layers as { id: string; filter?: unknown[] }[];
  const dimFill = layers.find((l) => l.id === 'ov-0-0-fill');
  const focusFill = layers.find((l) => l.id === 'ov-0-0-focus-fill');
  assert.deepEqual(dimFill?.filter, dimFilter);
  assert.deepEqual(focusFill?.filter, focusFilter);
});

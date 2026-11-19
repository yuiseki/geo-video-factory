import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_HEATMAP_COLORS,
  heatmapColorExpression,
  heatmapRadiusExpression,
  heatmapWeightExpression,
} from '../src/heatmap.js';

describe('heatmap helpers', () => {
  it('builds default interpolate heatmap-color expression', () => {
    const expr = heatmapColorExpression();
    assert.equal(expr[0], 'interpolate');
    assert.deepEqual(expr[1], ['linear']);
    assert.deepEqual(expr[2], ['heatmap-density']);
    assert.equal(expr[3], 0);
    assert.equal(expr[4], 'rgba(0, 0, 0, 0)');
    assert.ok(expr.length >= 5 + DEFAULT_HEATMAP_COLORS.length * 2 - 2);
  });

  it('builds custom heatmap-color expression from stops', () => {
    const stops: [number, string][] = [
      [0, 'rgba(0, 0, 0, 0)'],
      [0.5, '#38bdf8'],
      [1, '#f97316'],
    ];
    const expr = heatmapColorExpression(stops);
    assert.deepEqual(expr, [
      'interpolate',
      ['linear'],
      ['heatmap-density'],
      0, 'rgba(0, 0, 0, 0)',
      0.5, '#38bdf8',
      1, '#f97316',
    ]);
  });

  it('throws when custom stops are invalid', () => {
    assert.throws(() => heatmapColorExpression([[0, '#000000']]), /at least 2/);
    assert.throws(() => heatmapColorExpression([[0.5, '#000'], [0.5, '#fff']]), /strictly ascending/);
  });

  it('builds weight expression with or without property', () => {
    assert.equal(heatmapWeightExpression(), 1);
    assert.deepEqual(heatmapWeightExpression('count'), [
      'coalesce',
      ['to-number', ['get', 'count'], 0],
      0,
    ]);
  });

  it('builds zoom-scaled radius expression', () => {
    const expr = heatmapRadiusExpression(24);
    assert.equal(expr[0], 'interpolate');
    assert.deepEqual(expr[1], ['linear']);
    assert.deepEqual(expr[2], ['zoom']);
    assert.equal(expr[3], 7);
    assert.equal(expr[4], 12);
    assert.equal(expr[5], 10);
    assert.equal(expr[6], 24);
  });
});

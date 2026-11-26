import { test } from 'node:test';
import assert from 'node:assert/strict';
import { hasFullscreenPanel, labelAccent, labelPosition, lerpRect, panelExpandProgress } from '../src/overlay-position.js';

test('label offsets move the text in design pixels without moving the map anchor', () => {
  assert.deepEqual(labelPosition({ x: 800, y: 400 }, 2, [24, -40]), { left: '424px', top: '160px' });
  assert.deepEqual(labelPosition({ x: 800, y: 400 }, 2), { left: '400px', top: '200px' });
});

test('labelAccent uses default leader color when omitted and styles tag border when color is provided', () => {
  assert.deepEqual(labelAccent(), { leaderStroke: '#ffd36a', tagStyle: {} });
  assert.deepEqual(labelAccent('  '), { leaderStroke: '#ffd36a', tagStyle: {} });
  assert.deepEqual(labelAccent('#ff6b35'), {
    leaderStroke: '#ff6b35',
    tagStyle: { background: 'rgba(14, 22, 36, 0.90)', border: '3px solid #ff6b35' },
  });
});

test('hasFullscreenPanel detects when a fullscreen panel hides the underlying map credit', () => {
  assert.equal(hasFullscreenPanel([]), false);
  assert.equal(hasFullscreenPanel([{ type: 'panel', fullscreen: false }]), false);
  assert.equal(hasFullscreenPanel([{ type: 'panel', fullscreen: true }]), true);
});

test('panelExpandProgress and lerpRect smoothly expand and collapse a map card', () => {
  assert.equal(panelExpandProgress(undefined, 0.5), 0);
  assert.equal(panelExpandProgress([0.2, 0.4], 0.1), 0);
  assert.equal(panelExpandProgress([0.2, 0.4], 0.3), 0.5);
  assert.equal(panelExpandProgress([0.2, 0.4], 0.5), 1);
  assert.equal(panelExpandProgress([0.2, 0.4], 0.7, [0.6, 0.8]), 0.5);
  assert.equal(panelExpandProgress([0.2, 0.4], 0.9, [0.6, 0.8]), 0);
  assert.deepEqual(
    lerpRect({ x: 1000, y: 200, w: 400, h: 300 }, { x: 0, y: 0, w: 1920, h: 1080 }, 0.5),
    { x: 500, y: 100, w: 1160, h: 690 },
  );
});

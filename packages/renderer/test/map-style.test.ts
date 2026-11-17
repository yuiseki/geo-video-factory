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

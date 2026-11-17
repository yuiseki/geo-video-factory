import { test } from 'node:test';
import assert from 'node:assert/strict';
import { labelPosition } from '../src/overlay-position.js';

test('label offsets move the text in design pixels without moving the map anchor', () => {
  assert.deepEqual(labelPosition({ x: 800, y: 400 }, 2, [24, -40]), { left: '424px', top: '160px' });
  assert.deepEqual(labelPosition({ x: 800, y: 400 }, 2), { left: '400px', top: '200px' });
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { registerVideoE2E } from './video-e2e.js';

const item = {
  name: 'globe-hormuz-to-tokyo',
  fixture: 'globe-hormuz-to-tokyo.json',
  minimumDuration: 18.9,
} as const;
registerVideoE2E(item);

test('globe-hormuz-to-tokyo fixture configures globe projection from Hormuz to Tokyo', () => {
  const spec = JSON.parse(fs.readFileSync(`test/fixtures/${item.fixture}`, 'utf8')) as {
    projection?: string;
    shots: { duration: number }[];
  };
  assert.equal(spec.projection, 'globe');
  assert.equal(spec.shots.reduce((sum, s) => sum + s.duration, 0), 19);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { registerVideoE2E } from './video-e2e.js';

const item = {
  name: 'terrain-mt-fuji-seasonal',
  fixture: 'terrain-mt-fuji-seasonal.json',
  minimumDuration: 47.9,
  width: 1280,
  height: 720,
  prepareScript: 'test/e2e/prepare-fuji-seasonal.py',
  generatedProject: true,
} as const;
registerVideoE2E(item);

test('seasonal Fuji makes four continuous orbits with four season overlays', () => {
  const spec = JSON.parse(fs.readFileSync(`test/fixtures/${item.fixture}`, 'utf8')) as {
    shots: { duration: number; ease: string; keys: { center: number[]; bearing: number }[];
      overlays: { type: string; src?: string; bbox?: number[] }[] }[];
  };
  assert.equal(spec.shots.length, 1);
  const shot = spec.shots[0]!;
  assert.equal(shot.duration, 48);
  assert.equal(shot.ease, 'linear');
  assert.ok(shot.keys.every(key => key.center[0] === 138.7274 && key.center[1] === 35.3606));
  assert.equal(shot.keys.at(-1)!.bearing - shot.keys[0]!.bearing, 1440);
  assert.ok(shot.keys.slice(1).every((key, index) => key.bearing - shot.keys[index]!.bearing === 90));
  const images = shot.overlays.filter(overlay => overlay.type === 'image');
  assert.deepEqual(images.map(image => image.src), ['fuji-seasons/winter.png', 'fuji-seasons/spring.png', 'fuji-seasons/summer.png', 'fuji-seasons/autumn.png']);
  assert.ok(images.every(image => image.bbox && image.bbox[0]! < 138.7274 && image.bbox[2]! > 138.7274 && image.bbox[1]! < 35.3606 && image.bbox[3]! > 35.3606));
  assert.ok(fs.existsSync(item.prepareScript));
});

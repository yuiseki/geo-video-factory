import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { registerVideoE2E } from './video-e2e.js';

const videoName = 'buildings-asakusa-sumida-river';

export const buildingsAsakusaSumidaRiverVideoCase = {
  name: videoName,
  fixture: `${videoName}.json`,
  minimumDuration: 41.9,
  prepareScript: 'test/e2e/prepare-buildings-asakusa.py',
  generatedProject: true,
} as const;

registerVideoE2E(buildingsAsakusaSumidaRiverVideoCase);

test(`${videoName} is a registered flat-output E2E case`, () => {
  assert.match(videoName, /^buildings-/);
  assert.equal('outputPath' in buildingsAsakusaSumidaRiverVideoCase, false);
  assert.equal(buildingsAsakusaSumidaRiverVideoCase.generatedProject, true);
  assert.equal(buildingsAsakusaSumidaRiverVideoCase.minimumDuration, 41.9);
  assert.ok(fs.existsSync(path.join('test/fixtures', buildingsAsakusaSumidaRiverVideoCase.fixture)));
  assert.ok(fs.existsSync(buildingsAsakusaSumidaRiverVideoCase.prepareScript));
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const videoName = 'buildings-asakusa';
const fixturePath = path.join('test/fixtures', `${videoName}.json`);

export const buildingsAsakusaVideoCase = {
  name: videoName,
  fixture: `${videoName}.json`,
  minimumDuration: 4.9,
  prepareScript: 'test/e2e/prepare-buildings-asakusa.py',
  generatedProject: true,
} as const;

test(`${videoName} E2E case and output use the buildings- prefix`, () => {
  assert.match(videoName, /^buildings-/);
  assert.equal('outputPath' in buildingsAsakusaVideoCase, false,
    'the canonical E2E output is test/video/buildings-asakusa.mp4');
});

test(`${videoName} E2E reproduces the real-data render specification`, () => {
  const spec = JSON.parse(fs.readFileSync(fixturePath, 'utf8')) as {
    width: number;
    height: number;
    fps: number;
    base: string;
    world: boolean;
    dem: string;
    hillshade: boolean;
    plateauBuildings?: { manifest: string; heightOffset: number; workers: number };
    shots: {
      duration: number;
      from: { center: number[]; zoom: number; pitch: number; bearing: number };
      to: { center: number[]; zoom: number; pitch: number; bearing: number };
    }[];
  };
  assert.deepEqual(
    {
      width: spec.width,
      height: spec.height,
      fps: spec.fps,
      base: spec.base,
      world: spec.world,
      dem: spec.dem,
      hillshade: spec.hillshade,
      plateauBuildings: spec.plateauBuildings,
      shots: spec.shots,
    },
    {
      width: 640,
      height: 360,
      fps: 12,
      base: 'seamlessphoto',
      world: false,
      dem: 'gsi',
      hillshade: false,
      plateauBuildings: {
        manifest: 'assets/buildings-asakusa/manifest.json',
        heightOffset: -39,
        workers: 3,
      },
      shots: [{
        duration: 5,
        from: { center: [139.7918, 35.7028], zoom: 16, pitch: 56, bearing: -15 },
        to: { center: [139.7908, 35.6952], zoom: 16, pitch: 56, bearing: 10 },
      }],
    },
    'must retain the original real-data render settings without simplification',
  );

  assert.ok(spec.plateauBuildings?.manifest, 'PLATEAU manifest is required');
  assert.equal(buildingsAsakusaVideoCase.generatedProject, true);
  assert.ok(fs.existsSync(buildingsAsakusaVideoCase.prepareScript));
  assert.equal(fs.existsSync(path.join('test/fixtures', spec.plateauBuildings.manifest)), false,
    'runtime-generated PLATEAU data must not be committed under fixtures');
});

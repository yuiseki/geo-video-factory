import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const videoName = 'buildings-asakusa';
const fixturePath = path.join('test/fixtures', `${videoName}.json`);

export interface VideoCase {
  name: string;
  fixture: string;
  minimumDuration: number;
  width?: number;
  height?: number;
}

export const themaVideoCases: VideoCase[] = [
  { name: videoName, fixture: `${videoName}.json`, minimumDuration: 5.9 },
];

test(`${videoName} E2E case and output use the buildings- prefix`, () => {
  assert.match(videoName, /^buildings-/);
});

test(`${videoName} E2E uses a complete, repository-local PLATEAU fixture`, () => {
  const spec = JSON.parse(fs.readFileSync(fixturePath, 'utf8')) as {
    plateauBuildings?: { manifest: string };
  };
  assert.ok(spec.plateauBuildings?.manifest, 'PLATEAU manifest is required');
  const manifestPath = path.join('test/fixtures', spec.plateauBuildings.manifest);
  assert.ok(!manifestPath.split(path.sep).includes('tmp'), 'fixture must not read from tmp/');
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8')) as {
    format: string;
    tiles: { glb: string; ids?: string[] }[];
  };
  assert.equal(manifest.format, 'geo-video-factory.plateau-3d/1');
  assert.ok(manifest.tiles.length > 0, 'PLATEAU fixture must include model tiles');
  for (const tile of manifest.tiles) {
    assert.ok(fs.existsSync(path.resolve(path.dirname(manifestPath), tile.glb)), `missing committed GLB ${tile.glb}`);
    assert.ok(tile.ids?.length, `missing building IDs for ${tile.glb}`);
  }
});

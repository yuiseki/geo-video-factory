import { test } from 'node:test';
import assert from 'node:assert/strict';
import { clearNoDataPixels, imageTileRect, isNoDataPixel, parseImgTileUrl, tile2lat, tile2lng } from '../src/page/tile-math.js';

test('tile2lng / tile2lat give the NW corner of a web-mercator tile', () => {
  assert.equal(tile2lng(0, 0), -180);
  assert.equal(tile2lng(1, 0), 180);
  assert.equal(tile2lng(1, 1), 0);
  assert.ok(Math.abs(tile2lat(0, 0) - 85.0511287798) < 1e-6);
  assert.ok(Math.abs(tile2lat(1, 1)) < 1e-9);
  assert.ok(Math.abs(tile2lat(1, 0) + 85.0511287798) < 1e-6);
});

test('parseImgTileUrl reads id and z/x/y and rejects malformed urls', () => {
  assert.deepEqual(parseImgTileUrl('imgtile://ov-0-1/12/3590/1612'), { id: 'ov-0-1', z: 12, x: 3590, y: 1612 });
  assert.deepEqual(parseImgTileUrl('imgtile://a/0/0/0?x=1'), { id: 'a', z: 0, x: 0, y: 0 });
  assert.throws(() => parseImgTileUrl('imgtile://a/1/2'), /invalid imgtile url/);
  assert.throws(() => parseImgTileUrl('https://a/1/2/3'), /invalid imgtile url/);
});

test('imageTileRect places a bbox image inside the 256px tile, or returns null when disjoint', () => {
  // whole world bbox on the z0 tile covers the whole canvas
  const full = imageTileRect(0, 0, 0, [-180, -85.0511287798, 180, 85.0511287798])!;
  assert.ok(Math.abs(full.x) < 1e-6 && Math.abs(full.y) < 1e-6);
  assert.ok(Math.abs(full.w - 256) < 1e-6 && Math.abs(full.h - 256) < 1e-6);
  // a bbox ending at -10 degrees covers tile x=0 on z1 but not x=1 (a bbox that merely touches the edge still draws)
  assert.ok(imageTileRect(1, 0, 0, [-180, -85, -10, 85]));
  assert.equal(imageTileRect(1, 1, 0, [-180, -85, -10, 85]), null);
  // north-only bbox misses the south tile
  assert.equal(imageTileRect(1, 0, 1, [-180, 10, 180, 80]), null);
  // a bbox covering the left half of the tile is 128px wide
  const half = imageTileRect(1, 0, 0, [-180, 0, -90, 85])!;
  assert.ok(Math.abs(half.w - 128) < 1e-6);
});

test('isNoDataPixel: near-black and the (52,52,52) mosaic gray are no-data', () => {
  assert.equal(isNoDataPixel(0, 0, 0), true);
  assert.equal(isNoDataPixel(9, 9, 9), true);
  assert.equal(isNoDataPixel(10, 0, 0), false);
  assert.equal(isNoDataPixel(52, 52, 52), true);
  assert.equal(isNoDataPixel(55, 49, 52), true);
  assert.equal(isNoDataPixel(56, 52, 52), false);
  assert.equal(isNoDataPixel(200, 200, 200), false);
});

test('clearNoDataPixels zeroes alpha only for no-data pixels and reports the count', () => {
  const d = new Uint8ClampedArray([0, 0, 0, 255, 200, 10, 10, 255, 52, 52, 52, 255]);
  assert.equal(clearNoDataPixels(d), 2);
  assert.deepEqual([...d], [0, 0, 0, 0, 200, 10, 10, 255, 52, 52, 52, 0]);
});

test('perf budget: clearing a 256x256 tile takes well under 100 ms', () => {
  const d = new Uint8ClampedArray(256 * 256 * 4).fill(120);
  const t0 = performance.now();
  for (let i = 0; i < 20; i++) clearNoDataPixels(d);
  const per = (performance.now() - t0) / 20;
  assert.ok(per < 100, `${per.toFixed(1)} ms per tile`);
});

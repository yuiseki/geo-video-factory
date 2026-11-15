import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
  buildFrameTimes,
  chromiumGlArgs,
  contentType,
  parseSize,
  partitionFrameIndices,
  resolveProjectRoot,
  resolveRequestFile,
  resolveWorkerCount,
} from '../src/render.js';

test('chromiumGlArgs picks OS-appropriate ANGLE GPU backend and supports swiftshader override', () => {
  assert.deepEqual(chromiumGlArgs('win32', undefined), ['--use-gl=angle', '--use-angle=d3d11', '--ignore-gpu-blocklist']);
  assert.deepEqual(chromiumGlArgs('linux', undefined), ['--use-gl=angle', '--use-angle=gl-egl', '--ignore-gpu-blocklist']);
  assert.deepEqual(chromiumGlArgs('darwin', undefined), ['--use-gl=angle', '--use-angle=metal', '--ignore-gpu-blocklist']);
  assert.deepEqual(chromiumGlArgs('win32', 'swiftshader'), ['--use-angle=swiftshader', '--enable-unsafe-swiftshader']);
});

test('resolveProjectRoot uses explicit --project or parent of shots/ directory', () => {
  assert.equal(resolveProjectRoot('/tmp/p/shots/a.json'), path.resolve('/tmp/p'));
  assert.equal(resolveProjectRoot('/tmp/p/shots/a.json', '/tmp/custom'), path.resolve('/tmp/custom'));
  assert.equal(resolveProjectRoot('/tmp/other/a.json'), process.cwd());
});

test('resolveRequestFile routes renderer assets to packageRoot and project assets to projectRoot', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'gvf-srv-'));
  const pkg = path.join(tmp, 'pkg');
  const proj = path.join(tmp, 'proj');
  fs.mkdirSync(path.join(pkg, 'public'), { recursive: true });
  fs.mkdirSync(path.join(pkg, 'dist', 'src', 'page'), { recursive: true });
  fs.mkdirSync(path.join(proj, 'assets'), { recursive: true });
  fs.writeFileSync(path.join(pkg, 'public', 'index.html'), '<html></html>');
  fs.writeFileSync(path.join(pkg, 'dist', 'src', 'page', 'flyover.js'), '');
  fs.writeFileSync(path.join(pkg, 'dist', 'src', 'page', 'maplibre-gl-worker.mjs'), '');
  fs.writeFileSync(path.join(pkg, 'dist', 'src', 'lib.js'), '');
  fs.writeFileSync(path.join(proj, 'assets', 'photo.jpg'), 'jpg');
  fs.writeFileSync(path.join(tmp, 'secret.txt'), 'secret');

  assert.equal(resolveRequestFile('/page/index.html', pkg, proj), path.join(pkg, 'public', 'index.html'));
  assert.equal(resolveRequestFile('/page/flyover.js', pkg, proj), path.join(pkg, 'dist', 'src', 'page', 'flyover.js'));
  assert.equal(
    resolveRequestFile('/page/maplibre-gl-worker.mjs?v=6.18.0', pkg, proj),
    path.join(pkg, 'dist', 'src', 'page', 'maplibre-gl-worker.mjs'),
  );
  assert.equal(resolveRequestFile('/lib.js', pkg, proj), path.join(pkg, 'dist', 'src', 'lib.js'));
  assert.equal(resolveRequestFile('/assets/photo.jpg', pkg, proj), path.join(proj, 'assets', 'photo.jpg'));
  // Path traversal outside projectRoot must be rejected
  assert.equal(resolveRequestFile('/../secret.txt', pkg, proj), null);
  assert.equal(resolveRequestFile('/%2e%2e/secret.txt', pkg, proj), null);
  assert.equal(resolveRequestFile('/%E0%A4%A', pkg, proj), null);

  fs.rmSync(tmp, { recursive: true, force: true });
});

test('parseSize accepts positive integer dimensions and rejects malformed sizes', () => {
  assert.deepEqual(parseSize('1920x1080'), [1920, 1080]);
  assert.deepEqual(parseSize('1x1'), [1, 1]);
  for (const value of ['1920', 'x1080', '1920x', '0x1080', '-1x1080', '12.5x10', 'axb']) {
    assert.throws(() => parseSize(value), /size/i);
  }
});

test('buildFrameTimes is stable at decimal steps and validates its range', () => {
  assert.deepEqual(buildFrameTimes(0, 0.31, 0.1), [0, 0.1, 0.2, 0.3]);
  assert.deepEqual(buildFrameTimes(1, 1, 0.1), []);
  assert.throws(() => buildFrameTimes(-1, 1, 0.1), /from/i);
  assert.throws(() => buildFrameTimes(2, 1, 0.1), /range/i);
  assert.throws(() => buildFrameTimes(0, 1, 0), /step/i);
});

test('resolveWorkerCount defaults to 4 workers for 24+ frames and respects explicit counts', () => {
  assert.equal(resolveWorkerCount(2), 1);
  assert.equal(resolveWorkerCount(23), 1);
  assert.equal(resolveWorkerCount(24), 4);
  assert.equal(resolveWorkerCount(288), 4);
  assert.equal(resolveWorkerCount(288, 2), 2);
  assert.equal(resolveWorkerCount(2, 4), 2);
  assert.throws(() => resolveWorkerCount(10, 0), /workers/i);
  assert.throws(() => resolveWorkerCount(10, 1.5), /workers/i);
});

test('partitionFrameIndices splits frames into contiguous balanced ranges', () => {
  assert.deepEqual(partitionFrameIndices(10, 3), [
    [0, 4],
    [4, 7],
    [7, 10],
  ]);
  assert.deepEqual(partitionFrameIndices(4, 3), [
    [0, 2],
    [2, 3],
    [3, 4],
  ]);
  assert.deepEqual(partitionFrameIndices(0, 3), []);
});

test('MapLibre v6 ESM assets are served as JavaScript modules', () => {
  assert.equal(contentType('maplibre-gl.mjs'), 'text/javascript');
  assert.equal(contentType('maplibre-gl-worker.mjs'), 'text/javascript');
  assert.equal(contentType('style.css'), 'text/css');
  assert.equal(contentType('unknown.bin'), 'application/octet-stream');
});

test('flyover bundle includes MapLibre without a browser import map', () => {
  const html = fs.readFileSync(path.resolve('public/index.html'), 'utf8');
  assert.doesNotMatch(html, /importmap|maplibre-gl\.m?js/);
  assert.match(html, /await import\(['"]\/page\/flyover\.js['"]\)/);
  const source = fs.readFileSync(path.resolve('src/page/flyover.ts'), 'utf8');
  assert.match(source, /import \* as maplibregl from ['"]maplibre-gl['"]/);
  const bundle = fs.readFileSync(path.resolve('dist/src/page/flyover.js'), 'utf8');
  assert.doesNotMatch(bundle, /from\s+['"]maplibre-gl['"]/);
  assert.ok(bundle.length > 500_000, 'flyover.js should contain the MapLibre implementation');
  assert.ok(fs.statSync(path.resolve('dist/src/page/maplibre-gl-worker.mjs')).size > 500_000);
});

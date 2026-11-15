import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { buildFrameTimes, parseSize, resolveProjectRoot, resolveRequestFile } from '../src/render.js';

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
  fs.writeFileSync(path.join(pkg, 'dist', 'src', 'lib.js'), '');
  fs.writeFileSync(path.join(proj, 'assets', 'photo.jpg'), 'jpg');
  fs.writeFileSync(path.join(tmp, 'secret.txt'), 'secret');

  assert.equal(resolveRequestFile('/page/index.html', pkg, proj), path.join(pkg, 'public', 'index.html'));
  assert.equal(resolveRequestFile('/page/flyover.js', pkg, proj), path.join(pkg, 'dist', 'src', 'page', 'flyover.js'));
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

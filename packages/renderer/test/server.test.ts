import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { resolveProjectRoot, resolveRequestFile } from '../src/render.js';

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

  fs.rmSync(tmp, { recursive: true, force: true });
});

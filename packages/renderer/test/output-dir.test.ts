import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { freshFrames } from '../src/output-dir.js';

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'out-dir-'));

test('a new output gets an empty frames directory', () => {
  const out = path.join(tmp(), 'shot');
  const frames = freshFrames(out);
  assert.equal(frames, path.join(out, 'frames'));
  assert.deepEqual(fs.readdirSync(frames), []);
});

test('rendering again into the same output starts from empty frames, so no old frame leaks in', () => {
  const out = tmp();
  fs.mkdirSync(path.join(out, 'frames'));
  fs.writeFileSync(path.join(out, 'frames', '00099.png'), 'old');
  freshFrames(out);
  assert.deepEqual(fs.readdirSync(path.join(out, 'frames')), []);
});

test('what lies beside the frames (the voice cache, notes) is left alone', () => {
  const out = tmp();
  fs.mkdirSync(path.join(out, 'frames'));
  fs.writeFileSync(path.join(out, 'voice.json'), '{}');
  freshFrames(out);
  assert.ok(fs.existsSync(path.join(out, 'voice.json')));
});

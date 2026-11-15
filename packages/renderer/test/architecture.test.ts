import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

function sourceFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const file = path.join(dir, entry.name);
    return entry.isDirectory() ? sourceFiles(file) : entry.name.endsWith('.ts') ? [file] : [];
  });
}

test('renderer implementation modules stay below 400 lines', () => {
  const oversized = sourceFiles(path.resolve('src'))
    .filter((file) => !file.endsWith('types.ts'))
    .map((file) => ({ file: path.relative(process.cwd(), file), lines: fs.readFileSync(file, 'utf8').split('\n').length }))
    .filter(({ lines }) => lines > 400);

  assert.deepEqual(oversized, [], `split oversized modules by responsibility: ${JSON.stringify(oversized)}`);
});

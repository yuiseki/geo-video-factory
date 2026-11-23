import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

// ブラウザ側バンドルの大きさは、ページの読み込みと全 worker の起動時間に効く。
// 現状 (約 2.8MB、maplibre-gl を含む) に約 20% の余裕。上げるときは理由を書く。
const BUDGET = { 'flyover.js': 3_400_000 } as const;

for (const [file, max] of Object.entries(BUDGET)) {
  test(`bundle budget: page/${file} stays under ${max} bytes`, () => {
    const p = path.resolve('dist/src/page', file);
    assert.ok(fs.existsSync(p), `${p} missing: run npm run build`);
    const size = fs.statSync(p).size;
    assert.ok(size <= max, `${file} is ${size} bytes (budget ${max})`);
  });
}

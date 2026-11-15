---
name: geo-video-renderer
description: MapLibre、地理院タイル、Playwright、ffmpegを使い、ショットJSONから再現可能な地理動画を描画する。レンダラーの導入、ショット記述、タイル選択、フレーム書き出し、描画エラーの調査に使う。
---

# 地理動画レンダラー

レンダラーの本体は共通の TypeScript パッケージ `packages/renderer/` にあり、プロジェクトごとに JS/TS ファイルをコピーしない。新規プロジェクトには `assets/template/` の初期データ雛形（`shots/`, `characters/`, `assets/.gitkeep`, `.gitignore`）だけをコピーし、共通 CLI（`packages/renderer/dist/src/render.js`）に `--project <project-dir>`（または `shots/` 配下の JSON パス）を渡して実行する。

```bash
cd packages/renderer && npm install && npm run build
npx playwright install chromium-headless-shell
# 実行例 (リポジトリルートから)
node packages/renderer/dist/src/render.js <project>/shots/example.json --project <project> --out <project>/out/example --stills 2 --no-voice
```

章の並列結合・EXIF 座標抽出・立ち絵 PSD スプライト化などの Python ツールは `packages/pipeline/` を使う。

実データを読む書き出しはホストの資源制限ルールに従う。構図確認はまず `--stills`、本番は新しい `--out` を指定する。過去のフレームを混ぜない。GPU利用時はログのWebGL rendererを確認する。

- ショットJSONとoverlay： [references/shots.md](references/shots.md)
- 地理院写真、過去画像、出典： [references/gsi-tiles.md](references/gsi-tiles.md)
- タイル待ち、WebGL、音声、黒画面など： [references/troubleshooting.md](references/troubleshooting.md)

標高タイル (`gsidem` / `mapterhorn`) や 3D 地形表現の詳細は `geo-video-3d-terrain`、カメラの意味や速度は `geo-video-camera`、PLATEAUと建物補完は `geo-video-3d-buildings`、掛け合いと字幕は `geo-video-narration`、見た目の選択は `geo-video-visuals` の責務とする。レンダラー側へ個別作品の演出ルールを増やさず、再利用できるデータ形式と処理だけを置く。

---
name: geo-video-renderer
description: MapLibre、地理院タイル、Playwright、ffmpegを使い、ショットJSONから再現可能な地理動画を描画する。レンダラーの導入、ショット記述、タイル選択、フレーム書き出し、描画エラーの調査に使う。
---

# 地理動画レンダラー

実装の正本は `assets/template/`。新規プロジェクトではこの中身を作業ディレクトリへコピーし、既存プロジェクトでは必要な差分だけ移植する。テンプレートにはMapLibreのページ、Playwrightレンダラー、VOICEVOX連携、章パイプライン、写真位置、共通エフェクト、サンプルショットが含まれる。

```bash
cp -a <skill-dir>/assets/template/. <project>/
cd <project>
npm install
npx playwright install chromium-headless-shell
```

実データを読む書き出しはホストの資源制限ルールに従う。構図確認はまず `--stills`、本番は新しい `--out` を指定する。過去のフレームを混ぜない。GPU利用時はログのWebGL rendererを確認する。

- ショットJSONとoverlay： [references/shots.md](references/shots.md)
- 地理院写真、過去画像、出典： [references/gsi-tiles.md](references/gsi-tiles.md)
- タイル待ち、WebGL、音声、黒画面など： [references/troubleshooting.md](references/troubleshooting.md)

標高タイル (`gsidem` / `mapterhorn`) や 3D 地形表現の詳細は `geo-video-3d-terrain`、カメラの意味や速度は `geo-video-camera`、PLATEAUと建物補完は `geo-video-3d-buildings`、掛け合いと字幕は `geo-video-narration`、見た目の選択は `geo-video-visuals` の責務とする。レンダラー側へ個別作品の演出ルールを増やさず、再利用できるデータ形式と処理だけを置く。

---
name: geo-video-3d-terrain
description: 地理動画の3D地形と標高データ（gsidem、mapterhorn等）を設計・実装・検品する。標高タイルの選択と変換、高さ強調（exaggeration）、陰影起伏（hillshade）、地形上のラスタやラベルの描画不具合の解決に使う。
---

# 地理動画の 3D 地形と標高

MapLibre の 3D 地形に使う標高データ（DEM）の選択・変換と、地形の立体表現・描画上の制約を扱う。

## 責務と使い分け

- **標高タイル (`dem`) の選択と変換**: 国内の地理院標高タイル（`gsidem`）と全球対応の `mapterhorn` の使い分け、Terrarium 変換、出典表記。→ [references/dem-sources.md](references/dem-sources.md)
- **立体表現と描画の制約**: `exaggeration`（高さ強調）、`hillshade`（陰影起伏）、MapLibre 6.18.0 で確認した地形とラスタ/DOM 重ね合わせの仕様とトラブルシュート。→ [references/terrain-rendering.md](references/terrain-rendering.md)

## 関連スキルとの境界

- レンダラーの実行、ショット JSON 全体の書式、空中写真・背景タイルの選択は `geo-video-renderer` を使う。
- 地形を活かしたカメラ軌道（オービット、リビール、パララックス等）の設計は `geo-video-camera` を使う。
- 地形上に出す文字・線・図解・色の設計は `geo-video-visuals` を使う。

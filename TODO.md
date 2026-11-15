# TODO: PLATEAU 3D Buildings

## 1. PLATEAU 本体データの欠落補完 (`citygml-proxy`)

- [x] `packages/pipeline/plateau_3d.py` に `--citygml-geojson <path>` を追加する。
- [x] `manifest.json` に含まれない CityGML 建物 ID を抽出し、footprint + `height` から `kind: "citygml-proxy"` の GLB を生成する。
- [x] CityGML GeoJSON が `color`（オルソ調和色）を持つ場合は、詳細 PLATEAU タイルの `facade_colors` 未設定 ID にもその色を補完する（未調和の明色・屋上緑化色は `normalize_citygml_color` で自動調和）。
- [x] `citygml-proxy` は地表基準の押し出しなので、renderer で PLATEAU 詳細モデルの `heightOffset`（例: `-39m`）を掛けない。

## 2. OSM プロキシの重複判定改善

- [x] `build_osm_proxy_tiles()` に PLATEAU / CityGML footprint ポリゴン一覧を渡せるようにする。
- [x] `shapely` の `STRtree` で OSM ポリゴンと既存建物ポリゴンの交差面積比を計算し、`intersection_area / osm_area > 0.10` を除外する。
- [x] footprint が渡されない場合のみ、従来の `feature_centroids` 点内包判定にフォールバックする。

## 3. 無テクスチャ建物・テクスチャ建物の色・質感調整

- [x] 実データ出力（`out-v3`）の右上に出ている紫・緑系の強い色味と、国技館横アパホテル等の白飛び壁面の原因を特定して修正する。
  - パレット未設定時に 360° レインボー色相 (`setHSL`) と二重 sRGB ガンマ変換が掛かっていた不具合を廃止し、試作版 (`plateau-direct.js`) と同一の `max(r, g, b) <= 0.45` クランプ + 暖色 `(1.08, 0.96, 0.86)` / 寒色 `(0.86, 0.96, 1.08)` トーン + `0.84 + r2 * 0.30` 明度変化に統一。
  - `harmonize_orthophoto_color` / `normalize_citygml_color` で屋上緑化・防水シート由来の緑色相 (`0.19 <= h <= 0.48`) と紫色相 (`0.72 <= h <= 0.94`) の彩度を抑制。
  - テクスチャ付き PLATEAU マテリアルに対して `tuneMaterials` が `metalness` を `0.08` に上書きして拡散反射を 1.84 倍に白飛びさせていた問題を修正し、32×32 Rec.709 輝度解析 (`analyzeTextureTone`: `0.64` / `0.78` / `1.0`) と彩度減衰つき疑似外観シェーダ (`graySurface = 1.0 - smoothstep(0.07, 0.19, cmax - cmin)`) を適用。
- [x] `plateau_3d.py` にシーン中心付近 (`±0.003° × 0.0025°`) を `2048px`、遠景を `1024px` とする適応的テクスチャ縮小 (`tile_texture_limit`, Lanczos WebP `quality=88, method=3`) と GLB からの `CESIUM_RTC` 除去を統合。

## 4. 実データ検証とドキュメント同期

- [x] 両国・浅草周辺の実データ（PLATEAU 346 タイル + CityGML 補完 + OSM 補完）で再度動画を書き出し、フレームを目視確認する（`out-v4-final` で右上墨田区の紫・緑建物が解消し、国技館横アパホテル等の白壁に疑似窓と適正トーンが入ることを確認）。
- [x] `packages/README.md` と `.agents/skills/geo-video-3d-buildings/SKILL.md` を、実際に検証済みの CLI オプションと挙動に合わせて更新する。

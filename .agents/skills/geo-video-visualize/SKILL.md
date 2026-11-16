---
name: geo-video-visualize
description: 分析済みの統計値・空間データを、誤解を生まない2D/3Dコロプレス図（choropleth / fill-extrusion）、時系列比較地図として設計し、ショットJSONへ組み込むときに使う。配色・階級区切り・NoData分離・3D押し出し高さ・時系列の共通尺度・出典の設計に使う。
---

# 地理動画のデータ可視化（2D / 3D コロプレス）

統計値・集計値・空間分析の結果を、誤解を生まない **2D / 3D コロプレス図（`choropleth` / `fill-extrusion`）** として地図上に表現し、映像の説得力と視認性を底上げする。

## 責務と使い分け

- **配色・階級区切り・NoData・3D 押し出し設計**: 値の種類（量・率・増減・類型）に応じた配色、分位・等間隔の区切り、NoData と 0 の分離、時系列比較での共通尺度固定、`choropleth` オーバーレイ（`extrude` / `rise`）の書式。→ [references/choropleth-and-scale.md](references/choropleth-and-scale.md)
- **自治体・小地域ポリゴンの取得と結合**: 都道府県（Natural Earth）および市区町村・東京23区・町丁字（`yuiseki/estat-boundary-2020`）の取得方法、スキーマ、ディゾルブ、出典表記。→ [references/boundary-sources.md](references/boundary-sources.md)
- **実装本体**: `packages/renderer/src/choropleth.ts`（`choroplethColorExpression`, `choroplethHeightExpression`, `computeEqualBreaks`, `computeQuantileBreaks`、単体テスト: `packages/renderer/test/choropleth.test.ts`）

## 関連スキルとの境界

- 写真・テロップ・線・単色範囲・カード・画面効果などの一般演出は `geo-video-visuals` を使う。
- 構図・情報密度・色以外の判別性・縮小グレースケール検品は `geo-video-art-direction`（[visual-review.md](../geo-video-art-direction/references/visual-review.md)）を使う。
- 警戒区画・多系統比較・時系列診断などのコンソール風レイアウトは `geo-video-console-layout` を使う。
- レンダラーの実行・並列化・ショット JSON 全体の書式は `geo-video-renderer` を使う。
- 標高・海底地形（DEM / GEBCO 2024）の立体表現は `geo-video-3d-terrain` を使う。
- Sentinel-2 等の衛星データ・季節色度転写は `geo-video-satellite-imagery` を使う。

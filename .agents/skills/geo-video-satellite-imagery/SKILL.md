---
name: geo-video-satellite-imagery
description: Copernicus Sentinel-2 L2A などの衛星データ・衛星画像を取得・選別し、地理院オルソへの季節色度転写や経年・災害変化のテクスチャ生成、出典表記を行うときに使う。STAC API 検索、SCL 雲マスク判定、COG Range 読み込み、NDVI・CIE Lab 色転写、image オーバーレイの設計に使う。
---

# 地理動画の衛星画像・衛星データ

Sentinel-2 L2A などの衛星データを使って、地理院オルソへの季節色度転写（春夏秋冬・山焼き等）や衛星画像の比較・経年変化レイヤーを作成する。

## 責務と使い分け

- **Sentinel-2 L2A 検索・雲判定・季節色度転写**: Element84 Earth Search STAC API からのシーン検索、対象 `bbox` 内 SCL 雲マスク判定、HTTP Range による COG 読み込み、NDVI 植生マスクと CIE L\*a\*b\* 色転写による地理院オルソの季節変換、クレジット表記。→ [references/sentinel2-seasonal-ortho.md](references/sentinel2-seasonal-ortho.md)
- **実装本体**: `packages/pipeline/geo/seasonal_ortho.py`（単体テスト: `packages/pipeline/tests/test_seasonal_ortho.py`）

## 関連スキルとの境界

- レンダラーの実行、ショット JSON の全体書式、`seamlessphoto` / `bluemarble` 等の標準タイル設定は `geo-video-renderer` を使う。
- 標高タイル（`gsidem` / `mapterhorn`）や 3D 地形の立体表現・陰影起伏は `geo-video-3d-terrain` を使う。
- 外部写真・イラスト・過去地図の収集とライセンス監査は `geo-video-materials` を使う。
- 衛星テクスチャ上を周回・ズームするカメラ設計は `geo-video-camera` を使う。

# Sentinel-2 L2A 季節色度転写 (`seasonal_ortho.py`)

高精細な地理院空中写真（`seamlessphoto`）のテクスチャ・建物・道路を保ったまま、Copernicus Sentinel-2 L2A の季節ごとの色味（新緑、夏緑、紅葉、冬・山焼き後など）を転写して四季テクスチャを生成する手順。

## 1. 仕組みの概要

`packages/pipeline/seasonal_ortho.py` は以下の流れで季節テクスチャを生成する（GDAL / `rasterio` 不要、標準 Python + `numpy` + `Pillow` + `pyproj` のみ）。

1. **STAC API で候補シーンを検索 (`search_sentinel2_scene`)**
   - エンドポイント: `https://earth-search.aws.element84.com/v1/search`（認証不要）
   - コレクション: `sentinel-2-l2a`
2. **対象 `bbox` 内の SCL 雲・雲影率を実測 (`scl_clear_ratio`)**
   - シーン全体の `eo:cloud_cover` が低くても対象の山や街に局所雲が掛かることがあるため、SCL (`scl` COG) の対象 `bbox` 内だけ HTTP Range で取得し、雲・雲影・巻雲クラス（`3, 8, 9, 10`）を除外した晴天率（既定 `>= 0.95`）で選別する。
3. **HTTP Range で `visual` / `red` / `nir` COG を取得 (`read_cog_mercator_bbox`)**
   - GeoTIFF IFD（TileOffsets / TileByteCounts / Predictor=2 Deflate）を直接解析し、対象 `bbox` と重なるタイルだけを Range リクエストで取得する。
4. **NDVI 植生マスク＋CIE L\*a\*b\* 色度転写 (`build_vegetation_mask`, `blend_seasonal_chroma`)**
   - 植生域（対象季節の NDVI または地理院オルソの緑・茶色度）に限定し、L\*（明度・高周波テクスチャ）は地理院オルソを主体に保ちつつ、a\*・b\*（色度）と緩やかな明度差を季節データから転写する。これにより道路・建物・リフト等の人工物の色被りを防ぐ。

## 2. ショット JSON への組み込み

- 生成した季節 JPEG は `image` オーバーレイ（`bbox` にモザイクの `[west, south, east, north]` を指定）として重ね、`show` と `fade` でクロスフェードする。
- 原則として地理院 z16 相当以上（例: `2304 × 1792`）の解像度を維持し、縮小によるぼやけを防ぐ。
- `credits` に `"衛星色度：Copernicus Sentinel-2 L2A (YYYY-YYYY)"` 等を明記する（地理院タイルと地形の出典はレンダラーが自動付与する）。
- 1 周＝ 1 季節で複数周回させる場合、`cameraAt` は隣接キーフレーム間を最短角度（`[-180, 180)`）で補間するため、`bearing` は 90° 刻み（180° 未満）でキーフレームを分割する。

## 3. 単体テスト

```bash
python -m unittest discover -s packages/pipeline/tests -v
```

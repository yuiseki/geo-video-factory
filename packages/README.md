# 3D Buildings

3D Buildings は `pipeline/plateau_3d.py` で3D Tilesをシーン範囲に切り出し、GLBとローカルマニフェストに固定した後、rendererのMapLibreカスタムレイヤーで描画します。再生中にPLATEAUの配信サーバーへタイルを問い合わせません。

## データ準備

```sh
python3 packages/pipeline/plateau_3d.py 'https://example.invalid/tileset.json' \
  --bbox 139.775 35.680 139.810 35.718 \
  --out projects/example/assets/plateau \
  --orthophoto projects/example/assets/ortho.png \
  --osm-geojson projects/example/assets/osm-buildings.geojson \
  --seed example-v1
```

範囲は西・南・東・北の経度緯度（度）です。既定で並列数3、テクスチャ最大辺2048pxです。`--workers` と `--max-texture-dimension` で調整できます。出力先には `manifest.json` と `models/*.glb` が作られます。入力タイルは3D Tiles `region` の範囲判定で選び、親子が重複する場合は葉タイルだけを使用します。現在は `b3dm` と GLB、identity以外のタイル変換なし、GLB内に埋め込まれた画像を対象とします。非対応形式・変換・外部画像は不完全なモデルを出さずエラーにします。

### 外観パレットと OSM 補完

- `--orthophoto` を指定すると、`pipeline/building_appearance.py` が PLATEAU 各建物の footprint 領域（または重心の近傍）から代表色をサンプリングし、明度・彩度を調和させた `facade_colors` を `manifest.json` に記録します。元の写真テクスチャのみを持つ建物は `null` となり、元のテクスチャが保持されます。
- `--osm-geojson` を指定すると、PLATEAU の建物 ID および `feature_centroids` に含まれない OSM 建物ポリゴン（`Polygon` / `MultiPolygon`、穴あきポリゴン対応）を `height` または `building:levels × 3m` で押し出し、`_BATCHID` と `facade_colors` を備えたローカル GLB（`kind: "osm-proxy"`）として `manifest.json` へ追記します。
- レンダラー（`plateau-materials.ts`）は、テクスチャを持つマテリアルをそのまま保持し、テクスチャのないマテリアルおよび OSM プロキシに対して `_BATCHID` / `_FEATURE_ID_0` と `facade_colors` を用いた座標固定の疑似外観（階境界・窓・屋上グリッド）を適用します。

配信元が許す範囲で元データを保持してください。マニフェストには取得元URL、ハッシュ、タイルID、RTC中心、利用拡張を記録します。

## 動画への追加

ShotSpecのトップレベルに `plateauBuildings` を指定します。マニフェストとGLBは `--project` で指定するプロジェクトルートから参照します。

```json
{
  "plateauBuildings": {
    "manifest": "assets/plateau/manifest.json",
    "heightOffset": -39,
    "workers": 3
  },
  "shots": []
}
```

rendererは動画開始前にマニフェストとモデルを読み込み、WGS84 ECEFからローカルENUへ配置します。`heightOffset` はモデル全体の鉛直補正（メートル）で、既定値は0です。PLATEAUと地形の標高基準差が見える地域では、対象範囲に合わせて調整します。地図の地名やラスターは既存のMapLibreスタイルをそのまま使用します。

## 検証

```sh
python3 -m unittest discover -s packages/pipeline/tests -v
cd packages/renderer
npm run build
node --test --test-skip-pattern='E2E' dist/test/*.test.js
```

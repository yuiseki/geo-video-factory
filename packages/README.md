# 3D Buildings

3D Buildings は `pipeline/plateau_3d.py` で3D Tilesをシーン範囲に切り出し、GLBとローカルマニフェストに固定した後、rendererのMapLibreカスタムレイヤーで描画します。再生中にPLATEAUの配信サーバーへタイルを問い合わせません。

## データ準備

```sh
python3 packages/pipeline/plateau_3d.py 'https://example.invalid/tileset.json' \
  --bbox 139.775 35.680 139.810 35.718 \
  --out projects/example/assets/plateau \
  --orthophoto projects/example/assets/ortho.png \
  --citygml-geojson projects/example/assets/plateau-footprints.geojson \
  --osm-geojson projects/example/assets/osm-buildings.geojson \
  --seed example-v1
```

範囲は西・南・東・北の経度緯度（度）です。既定で並列数3、テクスチャ最大辺はシーン中心付近（`±0.003° × 0.0025°`）が 2048px、遠景タイルが 1024px の適応 WebP 変換（Lanczos, `quality=88, method=3`）です。`--workers` と `--max-texture-dimension` で調整できます。出力先には `manifest.json` と `models/*.glb` が作られ、GLB 内の `CESIUM_RTC` 拡張は `manifest.json` の `rtc` へ抽出した後に GLB JSON から除去されます。入力タイルは3D Tiles `region` の範囲判定で選び、親子が重複する場合は葉タイルだけを使用します。現在は `b3dm` と GLB、identity以外のタイル変換なし、GLB内に埋め込まれた画像を対象とします。非対応形式・変換・外部画像は不完全なモデルを出さずエラーにします。

### 外観パレットと OSM 補完

- `--orthophoto` を指定すると、`pipeline/building_appearance.py` が PLATEAU 各建物の footprint 領域（または重心の近傍）から代表色をサンプリングし、屋上緑化・防水シート等の緑・紫成分を抑えて明度・彩度を調和させた `facade_colors` を `manifest.json` に記録します。元の写真テクスチャのみを持つ建物は `null` となり、元のテクスチャが保持されます。
- `--osm-geojson` を指定すると、PLATEAU の建物 ID および `feature_centroids` に含まれない OSM 建物ポリゴン（`Polygon` / `MultiPolygon`、穴あきポリゴン対応）を `height` または `building:levels × 3m` で押し出し、`_BATCHID` と `facade_colors` を備えたローカル GLB（`kind: "osm-proxy"`）として `manifest.json` へ追記します。
- `--citygml-geojson` に CityGML から用意した建物 footprint と高さの FeatureCollection を渡すと、詳細タイルに ID がない建物を `citygml-proxy` として追加します。`height` はメートル、位置は WGS84 の経度・緯度で指定します。既存の `color` 属性（未調和の明色や屋上緑化色は自動調和）またはオルソ由来の色を利用します。CityGML 自体の GeoJSON 変換はこの CLI の対象外です。
- 両方の GeoJSON を渡した場合、OSM 建物と CityGML footprint の交差面積が OSM 建物の面積の 10% を超える建物は除外します。CityGML footprint を渡さない場合は従来の重心内包判定にフォールバックするため、部分重複の検出は不完全です。この空間判定には Shapely 2 が必要です。Draco 圧縮タイルの建物単位の位置・色の抽出には DracoPy 2 が必要です。両方とも `packages/pipeline/requirements-dev.txt` に記載しています。
- レンダラー（`plateau-materials.ts`）は、テクスチャを持つマテリアルに対して 32×32 Rec.709 輝度解析（`analyzeTextureTone`）で白飛びアトラスのトーンを 0.64 / 0.78 に抑えつつ、色差のある写真面（`cmax - cmin >= 0.19`）は元テクスチャをそのまま保ち、無彩色に近い白・灰の未撮影面やテクスチャのないマテリアル・プロキシに対して `_BATCHID` / `_FEATURE_ID_0` と `facade_colors` を用いた座標固定の疑似外観（暖色・寒色トーン、階境界・窓・屋上設備グリッド）を適用します。

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

rendererは動画開始前にマニフェストとモデルを読み込み、WGS84 ECEFからローカルENUへ配置します。`heightOffset` は PLATEAU 詳細モデルの鉛直補正（メートル）で、既定値は0です。地表を基準とする OSM・CityGML プロキシには適用しません。PLATEAUと地形の標高基準差が見える地域では、対象範囲に合わせて調整します。地図の地名やラスターは既存のMapLibreスタイルをそのまま使用します。

## 写真を都市モデルに置いて、人のいない街を描くための部品

`pipeline/` の次のモジュールは、写真 1 枚を PLATEAU に置き、人を消し、描いた場面を 1 本にまとめるまでの段を受け持ちます。どれも単体テストがあり、コマンドとしても呼べます (引数は各ファイルの冒頭)。

| モジュール | すること |
|---|---|
| `plateau_mesh.py` | `plateau_3d.py` が固定したタイルの全三角形を、1 つの東・北・上 (メートル) の座標系へ集めて `tris.npz` に書く |
| `skyline_match.py` | 建物と空の境界線を、モデルと写真の両方から読み、立ち位置と向きごとの費用を出す |
| `photo_place.py` | 写真 1 枚の位置・向き・上向き・ロール・画角を全幅探索し、`result.json`、重ね描き、`cams.json`、`mesh.npz` を書く |
| `people_removal.py` | 検出マスクを広げて人を埋める。見落としは箱で囲んで埋め直す (`refill`) |
| `camera_path.py` | 写真の位置と向きを基準にしたキーフレームから、フレームごとのカメラを作る |
| `frame_check.py` | 書き出したフレームの明るさを全部確かめ、暗いフレームを挙げる |
| `title_cards.py`、`scene_assembly.py` | 題字・地名・出典のカードを描き、場面をクロスフェードでつないで音量を整える |
| `ambient_bgm.py` | 正弦波と雑音だけで BGM を合成する |

`photo_place.py` が費用の低い偽の位置を返すことがあります。重ね描き (`overlay.jpg`) と、2 番目以降の候補との費用の差 (`result.json` の `rivals`) を必ず見ます。

## 検証

```sh
python3 -m unittest discover -s packages/pipeline/tests -v
cd packages/renderer
npm run build
node --test --test-skip-pattern='E2E' dist/test/*.test.js
```

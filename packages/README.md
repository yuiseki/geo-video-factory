# 3D Buildings

3D Buildings は `pipeline/plateau_3d.py` で3D Tilesをシーン範囲に切り出し、GLBとローカルマニフェストに固定した後、rendererのMapLibreカスタムレイヤーで描画します。再生中にPLATEAUの配信サーバーへタイルを問い合わせません。

## データ準備

```sh
python3 packages/pipeline/plateau_3d.py 'https://example.invalid/tileset.json' \
  --bbox 139.775 35.680 139.810 35.718 \
  --out projects/example/assets/plateau
```

範囲は西・南・東・北の経度緯度（度）です。既定で並列数3、テクスチャ最大辺2048pxです。`--workers` と `--max-texture-dimension` で調整できます。出力先には `manifest.json` と `models/*.glb` が作られます。入力タイルは3D Tiles `region` の範囲判定で選び、親子が重複する場合は葉タイルだけを使用します。現在は `b3dm` と GLB、identity以外のタイル変換なし、GLB内に埋め込まれた画像を対象とします。非対応形式・変換・外部画像は不完全なモデルを出さずエラーにします。

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

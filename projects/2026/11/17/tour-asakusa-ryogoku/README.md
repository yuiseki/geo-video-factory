# 浅草から両国へ空中散歩

浅草寺、東武浅草駅、アサヒグループ本社ビル、吾妻橋から、隅田川の上空を下流へ進み、浜町公園から両国国技館を見る地図映像です。カメラ経路は `packages/renderer/test/fixtures/buildings-asakusa-sumida-river.json` をもとにしています。

建物は `buildings-tokyo-sota` の方法を使います。PLATEAU のテクスチャ付き建物を優先し、地理院の建物外形で欠けた建物を補います。補完建物の高さには OSM の属性と PLATEAU による推定を、屋根には空中写真を使用します。推定した建物の高さ、屋根、窓や壁の模様は実測ではありません。PLATEAU の高さには既存 E2E と同じ -39 m の補正を使います。

## 生成

Node.js とレンダラーの依存関係、Python と `packages/pipeline/requirements-dev.txt`、ffmpeg、Playwright の Chromium が必要です。実データを読む実行にはホストの資源制限ルールを適用してください。

```sh
export GVF_PYTHON=/path/to/python
export OVERPASS_URL=https://overpass.yuiseki.net/api/interpreter
bash projects/2026/11/17/tour-asakusa-ryogoku/render.sh v0.1.1
```

生成した実データは `assets/` にキャッシュされます。描画結果は `out/v0.1.1/tour-asakusa-ryogoku.v0.1.1.mp4` に出力されます。地図と装飾を別々にレンダリングし、最後に合成します。

## 素材と出典

- [国土交通省 PLATEAU](https://www.mlit.go.jp/plateau/)：東京都 23 区 2025 年度 LOD2 建物モデル。
- [国土地理院 地理院タイル](https://maps.gsi.go.jp/development/ichiran.html)：空中写真、標高、建物の外形。
- [OpenStreetMap](https://www.openstreetmap.org/copyright)：建物属性。データは ODbL で提供されます。

データの更新時期は一致しません。取得時点によって建物や風景が変わります。

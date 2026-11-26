# 函館の地形と建物の試作

函館山と函館駅周辺に地理院の標高・航空写真・建物外形を重ねる試作です。建物は地理院ベクトルタイルから生成し、地理院 DEM の標高に配置します。高さは OSM の属性を優先し、値がない建物は既存の既定モデルから推定します。近隣 PLATEAU による較正は、この試作では行っていません。屋根は航空写真、外壁と窓は推定です。

## 再生成

`packages/pipeline` の依存関係、`packages/renderer` のビルド、Chromium、ffmpeg が必要です。実データを読むため、ホストの資源上限に従って実行します。

```sh
OVERPASS_URL=https://overpass.yuiseki.net/api/interpreter python projects/2026/11/17/hakodate-terrain-buildings/prepare.py
node packages/renderer/dist/src/render.js projects/2026/11/17/hakodate-terrain-buildings/shots/overview.json --project projects/2026/11/17/hakodate-terrain-buildings --out projects/2026/11/17/hakodate-terrain-buildings/out/overview-v1 --stills 2 --no-voice
```

生成したモデル、取得したタイル、OSM の建物データは `assets/` にキャッシュします。出力先は新しい名前を指定してください。

## 出典

- 建物外形：国土地理院の地理院ベクトルタイル
- 空中写真・標高：国土地理院の地理院タイルを加工
- 建物の属性：© OpenStreetMap contributors（ODbL）

建物の高さ、屋根の形、外壁および窓の模様には推定を含みます。実測や防災上の判断には使えません。

## 試作 v0.1.0

建物外形 49,049 件、OSM 建物情報 40,401 件を取得しました。`shots/magic-candidates.json` と v2 から v9 で海上の方角・ズーム・傾きを比較しました。`shots/magic-motion.json` は航空写真の継ぎ目が見えない短い動きです。函館山の山頂と市街地は入りますが、山の南側は画面外に切れます。山全体を収める画角では海上の航空写真の境界が残り、引き続き画角の調整が必要です。

## v0.2.0

`shots/hakodate-city-terrain.json` は、確認済みの函館山と市街地の構図から、12秒かけて緩やかに回り込みながら少し寄ります。出典と建物の推定表現を表示します。無音です。対象範囲、航空写真の継ぎ目、建物の高さや外壁の推定に注意してください。

## v0.3.0

`shots/hakodate-reveal.json` は、真上からズームインし、同じ中心・ズームのままカメラを傾けてから、地理院の建物外形から生成した建物を立ち上げます。続いて屋根の航空写真と推定外壁を段階的に表示します。尺は27秒で、無音です。海上の空中写真にはタイルの切れ目が入る場合があります。

# 標高データ (DEM) の選択と変換

テンプレート（`page/lib.js` の `DEMS` / `demSourceSpec`）では、ショット JSON のトップレベル `"dem"` で標高ソースを切り替える。既定は `"gsi"`。

## 比較と使い分け

| `dem` | 対象範囲 | 最大ズーム | 形式・タイルサイズ | 変換プロトコル | 主な用途 |
|---|---|---|---|---|---|
| `gsi` | 日本国内 | z14 | PNG (`dem_png`), 256px | `gsidem://`（ブラウザ内で Terrarium 変換） | 日本国内の地形、基盤地図情報に基づく精密な解説 |
| `mapterhorn` | 全球 | z15 | WebP, 512px | 不要（そのまま Terrarium 形式） | 海外の地形、日本と海外をシームレスにつなぐ広域ショット |

---

## 1. 地理院 標高タイル (`gsi` / `gsidem`)

- **タイル**: `https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png`（基盤地図情報の数値標高モデル、z14 まで）。
- **エンコーディング**:
  - $x = R \times 2^{16} + G \times 2^8 + B$
  - $x < 2^{23}$ なら標高 $h = x \times 0.01\text{ m}$
  - $x > 2^{23}$ なら標高 $h = (x - 2^{24}) \times 0.01\text{ m}$
  - $x = 2^{23}$（RGB `128, 0, 0`）は「値なし」（海・国外・欠損）。
- **`gsidem` プロトコルによる変換**:
  - MapLibre GL JS は地理院独自の標高 PNG 形式を直接読めない。
  - `page/flyover.js` の `registerGsiDem()` が `gsidem://` プロトコルを登録し、`page/lib.js` の `gsiToTerrarium()` と `terrariumRGB()` を通してブラウザ内で Terrarium 形式に変換している。
  - 値なし（RGB `128, 0, 0`）および 404（海・国外）は `0 m`（Terrarium RGB `128, 0, 0`）に置換する。変換を挟まず MapLibre の `custom` エンコーディング等を使うと、値なしが **83,886 m の針** として立ち上がる。
- **出典表記**:
  - 自動で `標高：国土地理院(地理院タイル「標高タイル」)を加工` が画面右下に入る。
  - 公開前には国土地理院の「地理院タイル利用規約」を確認する。

---

## 2. Mapterhorn (`mapterhorn`)

- **概要**: Copernicus DEM (GLO-30) や各国の高精細 LiDAR 等のオープン標高データを統合した全球タイルセット。API キー不要で利用できる。
- **タイル**: `https://tiles.mapterhorn.com/{z}/{x}/{y}.webp`
- **仕様**:
  - 形式: WebP
  - タイルサイズ: `512` px（`demSourceSpec('mapterhorn')` で指定）
  - エンコーディング: `terrarium`（$h = R \times 256 + G + B / 256 - 32768$）。変換プロトコルは不要で MapLibre の `raster-dem` にそのまま渡せる。
- **使い分けの目安**:
  - ホルムズ海峡や海外都市など、地理院タイルがカバーしない海外の地形を 3D にするとき。
  - 日本国内から海外へ一気に引く／移動するトランジションショット（`gsi` だと国外が 0 m の平面になるため）。
- **出典表記**:
  - 自動で `標高：© Mapterhorn and DEM source contributors` が画面右下に入る。
  - 動画の概要欄にも出典リンク（`https://mapterhorn.com/attribution`）を明記する。

---

## 3. その他の注意点

- **OSM / Valhalla の `/height` は使わない**: 公開している `valhalla.yuiseki.net` には標高データが入っておらず `null` が返るため、地形や断面には必ず上記の DEM タイルを使う。
- **過去の地形を現在の DEM で表す場合**: 現代の標高データで昔の地形・海岸線やシミュレーション結果を描く場合は、「現在の地形データをもとにした表現」であることを画面・声・概要欄で明示する。
- **サーバー負荷**: タイルサーバーに過度の負荷をかけない。書き出しは同時に 1 本（またはホスト規則の上限内）に抑える。

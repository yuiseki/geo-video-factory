# 自治体・小地域ポリゴン境界の取得と結合

コロプレス図（`choropleth` オーバーレイ）を作るには、統計値を持つ GeoJSON ポリゴンが必要になる。粒度に合わせた境界ソースの選び方と、取得・絞り込み・属性結合・出典表記の標準手順をまとめる。

## 1. 粒度の選び方

| 対象粒度 | 推奨ソース | 特徴・ライセンス |
|---|---|---|
| **世界・都道府県** | Natural Earth (`ne_10m_admin_1_states_provinces`) | 1:10M スケール、軽量で全国俯瞰に十分。**Public Domain** |
| **市区町村・東京23区・町丁字** | `yuiseki/estat-boundary-2020` (e-Stat 令和2年国勢調査 小地域) | 全国 47 都道府県、232,019 小地域ポリゴン＋人口・世帯数付き。**CC BY 4.0**（OSM の ODbL と異なり、生成物への継承義務がない） |

## 2. 都道府県ポリゴン: Natural Earth

- リポジトリ: `nvkelso/natural-earth-vector`
- Raw GeoJSON URL:
  `https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_1_states_provinces.geojson`
- 日本の都道府県を抽出するときの主なプロパティ:
  - `adm0_a3 == "JPN"`（国コードで日本のみ抽出）
  - `iso_3166_2`（`"JP-01"` 〜 `"JP-47"`。例: 東京都は `"JP-13"`）
  - `name`, `name_ja`

都道府県コード（`01`〜`47`）または `iso_3166_2`（`JP-01`〜`JP-47`）をキーにして統計値を `properties` へ結合し、`projects/.../assets/` 配下に保存する（不要な国や巨大プロパティは削って軽量化する）。

## 3. 東京23区・市区町村・町丁字: `yuiseki/estat-boundary-2020`

- Hugging Face Dataset: `https://huggingface.co/datasets/yuiseki/estat-boundary-2020`
- 形式: 都道府県別 GeoParquet（`parquet/r2ka01.parquet` 〜 `parquet/r2ka47.parquet`、東京都は `parquet/r2ka13.parquet`）および元 Shapefile（`shape/A002005212020DDSWC01.zip` 〜 `47.zip`）
- 測地系: JGD2000（経緯度、`geometry` 列は WKB）
- 主なカラム（**すべて文字列型**。数値型に推論させると `CITY` の先頭ゼロや型が崩れるので注意）:
  - `KEY_CODE`: 小地域キー（`PREF` + `CITY` + `S_AREA`）
  - `PREF`, `CITY`, `S_AREA`: 都道府県・市区町村・小地域コード（`PREF` + `CITY` が 5 桁の全国地方公共団体コードに相当。例: 東京都特別区部は `PREF = '13'`、`CITY` が `'101'`〜`'123'`）
  - `PREF_NAME`, `CITY_NAME`, `S_NAME`: 例 `東京都`, `千代田区`, `神田三崎町一丁目`
  - `JINKO`, `SETAI`: 令和2年国勢調査の人口・世帯数

### DuckDB 等での取得・GeoJSON 変換の考え方

1. **町丁・字単位で使う場合**: `parquet/r2ka13.parquet` 等を読み、`CITY BETWEEN '101' AND '123'`（または `CITY_NAME`）で対象区を絞り、`JINKO` などを数値変換して統計値を結合し GeoJSON 化する。
2. **東京23区・市区町村単位で使う場合**: 小地域ポリゴンを `PREF`, `CITY`, `CITY_NAME` ごとに `ST_Union_Agg(ST_GeomFromWKB(geometry))` 等でディゾルブ（結合）し、必要に応じてトポロジを保って簡略化してから GeoJSON へ書き出す。
3. **無名・水面調査区**: `S_NAME` が空の 410 件や `水面調査区` を含むことがあるため、描画目的によっては除外または NoData（`null`）扱いにする。

```sql
-- 例: DuckDB spatial で東京都23区の区単位ポリゴン＋人口を作る概略
LOAD spatial;
SELECT
  PREF || CITY AS lg_code,
  CITY_NAME,
  SUM(CAST(JINKO AS INTEGER)) AS jinko_2020,
  ST_Union_Agg(ST_GeomFromWKB(geometry)) AS geom
FROM read_parquet('https://huggingface.co/datasets/yuiseki/estat-boundary-2020/resolve/main/parquet/r2ka13.parquet')
WHERE CAST(CITY AS INTEGER) BETWEEN 101 AND 123
GROUP BY PREF, CITY, CITY_NAME;
```

## 4. レンダラーへ渡す前のチェック

- `packages/renderer/` の `choropleth` オーバーレイは `property` に数値（または欠損時 `null`）を期待する。文字列のまま残すと色・高さ計算で欠損扱いになるため、GeoJSON 書き出し時に数値型へ変換しておく。
- 画面が重くなる場合は、表示ズームに対して過剰な頂点数を簡略化（simplify）する。
- **出典表記**:
  - Natural Earth を使った場合: `Natural Earth`（Public Domain）
  - `yuiseki/estat-boundary-2020` を使った場合:
    `出典：「令和2年国勢調査 小地域（町丁・字等別）境界データ」（政府統計の総合窓口(e-Stat) https://www.e-stat.go.jp/ ）`（CC BY 4.0、Parquet 化・加工がある場合はその旨も記す）
